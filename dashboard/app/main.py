import sys

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig


def main() -> None:
    """
    Κεντρικό σημείο εκκίνησης του MoonHard Remote Dashboard.
    """

    if len(sys.argv) == 3 and sys.argv[1] == "--terminal-self-test":
        from app.terminal_smoke import TerminalSmokeTest
        raise SystemExit(TerminalSmokeTest.run(sys.argv[2]))

    if len(sys.argv) == 3 and sys.argv[1] == "--appsettings-self-test":
        from app.appsettings_smoke import AppSettingsSmokeTest
        raise SystemExit(AppSettingsSmokeTest.run(sys.argv[2]))

    if len(sys.argv) > 1 and sys.argv[1] == "--appsettings":
        from app.appsettings_cli import main as appsettings_main
        raise SystemExit(appsettings_main(sys.argv[2:]))

    if len(sys.argv) == 3 and sys.argv[1] == "--ssms-self-test":
        from app.sql_smoke import SqlSmokeTest
        raise SystemExit(SqlSmokeTest.run(sys.argv[2]))

    if len(sys.argv) > 1 and sys.argv[1] == "--ssms":
        from app.sql_cli import main as sql_main
        raise SystemExit(sql_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--terminal":
        from app.terminal_cli import main as terminal_main
        raise SystemExit(terminal_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--provider-transmitted":
        from app.provider_transmitted_cli import main as transmitted_main
        raise SystemExit(transmitted_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--database":
        from app.database_cli import main as database_main
        raise SystemExit(database_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--backup":
        from app.backup_cli import main as backup_main
        raise SystemExit(backup_main(sys.argv[2:]))

    if len(sys.argv) == 3 and sys.argv[1] == "--overview-self-test":
        from app.overview_smoke import OverviewSmokeTest
        raise SystemExit(OverviewSmokeTest.run(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "--overview":
        from app.overview_cli import main as overview_main
        raise SystemExit(overview_main(sys.argv[2:]))

    config = DashboardConfig()
    DashboardLoggerConfig.setup_logging(config.log_dir)

    # Εγκαθιστά πρώτα την εργονομική Provider προβολή ώστε κάθε νέο
    # Manage window να χρησιμοποιεί το compact layout με μεγάλο results area.
    from app.provider_dashboard_extension import install_provider_dashboard_extension
    install_provider_dashboard_extension()

    # Επεκτείνει το Database tab με την ελεγχόμενη Διαγραφή διπλών ΜΑΡΚ.
    from app.database_duplicate_mark_extension import install_database_duplicate_mark_extension
    install_database_duplicate_mark_extension()

    # Εγκαθιστά το Registry tab και το Registry WebSocket result routing
    # πριν δημιουργηθεί το κύριο Dashboard instance.
    from app.registry_dashboard_extension import install_registry_dashboard_extension
    install_registry_dashboard_extension()

    from app.dashboard_app import MoonHardDashboardApp
    app = MoonHardDashboardApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
