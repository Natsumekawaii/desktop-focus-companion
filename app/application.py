"""Application setup and lifecycle management."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import __version__
from app.application_controller import ApplicationController
from app.core.app_icon_manager import AppIconError, AppIconManager
from app.core.logging_config import configure_logging
from app.core.paths import ApplicationPaths
from app.core.theme import DEFAULT_COLOR_THEME, get_theme_manager
from app.data.database import Database, DatabaseError
from app.data.database_settings_repository import DatabaseSettingsRepository
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.data.gamification_repository import GamificationRepository
from app.data.settings_repository import SettingsRepository
from app.focus_mode import FocusMode
from app.gamification import GamificationService
from app.gamification.gamification_controller import GamificationController
from app.i18n import get_localization, tr
from app.integration.application_preferences_controller import (
    ApplicationPreferencesController,
)
from app.integration.single_instance import SingleInstanceGuard
from app.integration.startup_manager import WindowsStartupManager
from app.integration.tray_controller import TrayController
from app.pet.pet_asset_manager import PetAssetManager
from app.pet.pet_controller import PetController
from app.pet.pet_window import PetWindow
from app.statistics import StatisticsService
from app.timer.active_session_store import ActiveSessionStore
from app.timer.focus_session_manager import FocusSessionManager
from app.timer.focus_timer import FocusTimer
from app.ui.dashboard import DashboardWindow
from app.ui.dashboard_controller import DashboardController
from app.ui.info_bubble import install_animated_tooltips
from app.ui.quick_panel import FocusPanel
from app.ui.quick_panel_controller import FocusPanelController

PACKAGED_SMOKE_TEST_ENV = "DESKTOP_FOCUS_COMPANION_SMOKE_TEST"
from app.ui.settings_dialog import SettingsDialog
from app.ui.subject_dialog import FocusItemDialog

APPLICATION_NAME = "Desktop Focus Companion"
ORGANIZATION_NAME = "Desktop Focus Companion"


@dataclass(slots=True)
class ApplicationRuntime:
    """Keep the complete UI, service, and controller object graph alive."""

    pet_window: PetWindow
    settings_dialog: SettingsDialog
    pet_controller: PetController
    database: Database
    focus_item_repository: FocusItemRepository
    focus_session_repository: FocusSessionRepository
    database_settings_repository: DatabaseSettingsRepository
    session_manager: FocusSessionManager
    quick_panel: FocusPanel
    focus_item_dialog: FocusItemDialog
    quick_panel_controller: FocusPanelController
    application_controller: ApplicationController
    statistics_service: StatisticsService
    dashboard_window: DashboardWindow
    dashboard_controller: DashboardController
    gamification_repository: GamificationRepository
    gamification_service: GamificationService
    gamification_controller: GamificationController
    startup_manager: WindowsStartupManager
    application_preferences_controller: ApplicationPreferencesController
    tray_controller: TrayController


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Create the Qt application and configure stable application metadata."""
    existing_application = QApplication.instance()
    if existing_application is not None:
        if not isinstance(existing_application, QApplication):
            raise RuntimeError("A non-GUI Qt application already exists.")
        install_animated_tooltips(existing_application)
        return existing_application

    application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName(APPLICATION_NAME)
    application.setApplicationVersion(__version__)
    application.setOrganizationName(ORGANIZATION_NAME)
    try:
        default_icon = AppIconManager(ApplicationPaths.discover()).resolve(None)
    except AppIconError:
        pass
    else:
        application.setWindowIcon(QIcon(str(default_icon.path)))
    application.setStyle("Fusion")
    install_animated_tooltips(application)
    localization = get_localization()
    theme_manager = get_theme_manager()
    localization.language_changed.connect(theme_manager.set_language)
    theme_manager.set_language(localization.language)
    theme_manager.set_theme(DEFAULT_COLOR_THEME)
    return application


def build_runtime(paths: ApplicationPaths | None = None) -> ApplicationRuntime:
    """Build the application object graph with explicit infrastructure boundaries."""
    application_paths = paths or ApplicationPaths.discover()
    application_paths.prepare_data_directory()
    settings_repository = SettingsRepository(application_paths.settings_path)
    settings = settings_repository.load()
    get_localization().set_language(settings.language)
    get_theme_manager().set_theme(settings.color_theme)
    database = Database(application_paths.database_path)
    database.initialize()
    focus_item_repository = FocusItemRepository(database)
    focus_item_repository.ensure_defaults()
    focus_session_repository = FocusSessionRepository(database)
    focus_session_repository.ensure_minute_precision()
    database_settings_repository = DatabaseSettingsRepository(database)
    gamification_repository = GamificationRepository(database)
    active_session_store = ActiveSessionStore(application_paths.active_session_path)
    session_manager = FocusSessionManager(
        FocusTimer(),
        focus_item_repository,
        focus_session_repository,
        active_session_store,
    )
    statistics_service = StatisticsService(focus_session_repository)
    pet_window = PetWindow()
    settings_dialog = SettingsDialog(parent=pet_window)
    settings_dialog.set_data_location(application_paths.data_dir)
    quick_panel = FocusPanel(parent=pet_window)
    quick_panel.set_default_focus(
        FocusMode(settings.default_focus_mode),
        settings.default_focus_target_seconds,
    )
    focus_item_dialog = FocusItemDialog(parent=quick_panel)
    dashboard_window = DashboardWindow(statistics_service.local_timezone)
    asset_manager = PetAssetManager(application_paths)
    app_icon_manager = AppIconManager(application_paths)
    pet_controller = PetController(
        window=pet_window,
        settings_dialog=settings_dialog,
        settings_repository=settings_repository,
        asset_manager=asset_manager,
        app_icon_manager=app_icon_manager,
    )
    pet_controller.focus_timer_preferences_updated.connect(
        quick_panel.set_default_focus
    )
    quick_panel_controller = FocusPanelController(
        panel=quick_panel,
        focus_item_dialog=focus_item_dialog,
        pet_window=pet_window,
        session_manager=session_manager,
        focus_item_repository=focus_item_repository,
        statistics_service=statistics_service,
        focus_session_repository=focus_session_repository,
    )
    pet_window.focus_panel_requested.connect(quick_panel_controller.toggle_panel)
    dashboard_controller = DashboardController(
        window=dashboard_window,
        statistics_service=statistics_service,
        focus_item_repository=focus_item_repository,
        focus_session_repository=focus_session_repository,
    )
    quick_panel_controller.session_finished.connect(lambda _: dashboard_controller.refresh())
    quick_panel_controller.focus_items_changed.connect(dashboard_controller.refresh)
    dashboard_controller.data_changed.connect(quick_panel_controller.refresh_summary)
    gamification_service = GamificationService(
        statistics_service=statistics_service,
        settings_repository=database_settings_repository,
        gamification_repository=gamification_repository,
    )
    gamification_controller = GamificationController(
        service=gamification_service,
        quick_panel=quick_panel,
        dashboard=dashboard_window,
        settings_dialog=settings_dialog,
    )
    quick_panel_controller.session_finished.connect(lambda _: gamification_controller.refresh())
    quick_panel_controller.focus_items_changed.connect(gamification_controller.refresh)
    dashboard_controller.data_changed.connect(gamification_controller.refresh)
    application_controller = ApplicationController(
        pet_window=pet_window,
        pet_controller=pet_controller,
        session_manager=session_manager,
        quick_panel_controller=quick_panel_controller,
    )
    startup_manager = WindowsStartupManager(application_paths.project_root)
    application_preferences_controller = ApplicationPreferencesController(
        settings_dialog=settings_dialog,
        pet_controller=pet_controller,
        startup_manager=startup_manager,
    )
    tray_controller = TrayController(
        icon_path=str(
            app_icon_manager.resolve(pet_controller.settings.custom_app_icon_path).path
        ),
        pet_window=pet_window,
        pet_controller=pet_controller,
        quick_panel_controller=quick_panel_controller,
        dashboard_controller=dashboard_controller,
        application_controller=application_controller,
    )
    gamification_controller.notification_requested.connect(tray_controller.notify)
    return ApplicationRuntime(
        pet_window=pet_window,
        settings_dialog=settings_dialog,
        pet_controller=pet_controller,
        database=database,
        focus_item_repository=focus_item_repository,
        focus_session_repository=focus_session_repository,
        database_settings_repository=database_settings_repository,
        session_manager=session_manager,
        quick_panel=quick_panel,
        focus_item_dialog=focus_item_dialog,
        quick_panel_controller=quick_panel_controller,
        application_controller=application_controller,
        statistics_service=statistics_service,
        dashboard_window=dashboard_window,
        dashboard_controller=dashboard_controller,
        gamification_repository=gamification_repository,
        gamification_service=gamification_service,
        gamification_controller=gamification_controller,
        startup_manager=startup_manager,
        application_preferences_controller=application_preferences_controller,
        tray_controller=tray_controller,
    )


def run_application(arguments: Sequence[str] | None = None) -> int:
    """Start the Desktop Focus Companion event loop and return its exit code."""
    application = create_application(arguments)
    application.setQuitOnLastWindowClosed(False)
    paths = ApplicationPaths.discover()
    paths.prepare_data_directory()
    get_localization().set_language(SettingsRepository(paths.settings_path).load().language)
    configure_logging(paths.logs_dir)
    logging.getLogger(__name__).info("Desktop Focus Companion %s starting", __version__)
    instance_guard = SingleInstanceGuard(paths.instance_lock_path)
    if not instance_guard.acquire():
        from PySide6.QtWidgets import QMessageBox

        logging.getLogger(__name__).info(
            "Second Desktop Focus Companion instance exited safely"
        )
        QMessageBox.information(None, tr("app.name"), tr("startup.already_running"))
        return 0
    try:
        runtime = build_runtime(paths)
    except Exception as startup_error:
        logging.getLogger(__name__).exception("Desktop Focus Companion startup failed")
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            tr("startup.recovery_title") if isinstance(startup_error, DatabaseError) else tr("app.name"),
            (
                f"{tr('startup.database_failed')}\n\n{tr('startup.database_preserved')}"
                if isinstance(startup_error, DatabaseError)
                else tr("startup.failed")
            ),
        )
        instance_guard.release()
        return 1
    application.aboutToQuit.connect(runtime.pet_controller.flush_settings)
    runtime.pet_controller.start()
    if os.environ.get(PACKAGED_SMOKE_TEST_ENV) == "1":
        QTimer.singleShot(1000, application.quit)
    try:
        return application.exec()
    finally:
        logging.getLogger(__name__).info(
            "Desktop Focus Companion %s shutting down", __version__
        )
        instance_guard.release()
