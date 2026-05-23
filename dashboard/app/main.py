from app.config import DashboardConfig
from app.dashboard_app import MoonHardDashboardApp
from app.logger_config import DashboardLoggerConfig


def main() -> None:
    """
    Κεντρικό σημείο εκκίνησης του MoonHard Remote Dashboard.
    """

    config = DashboardConfig()
    DashboardLoggerConfig.setup_logging(config.log_dir)

    app = MoonHardDashboardApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()