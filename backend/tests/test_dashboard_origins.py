from dataclasses import replace


def test_dashboard_config_advertises_only_primary_origin_by_default(cloud):
    settings = replace(cloud.settings, dashboard_origin="https://dashboard.example.com")
    config = settings.dashboard()
    assert config["auth"]["allowed_origins"] == ["https://dashboard.example.com"]
    assert (
        config["auth"]["callback_url"] == "https://dashboard.example.com/auth/callback"
    )
    assert "allowed_origins" not in settings.public()["auth"]


def test_local_dashboard_is_opt_in_and_never_enabled_in_production(cloud):
    settings = replace(
        cloud.settings,
        dashboard_origin="https://dashboard.example.com",
        environment="dev",
        enable_local_dashboard=True,
    )
    assert settings.dashboard()["auth"]["allowed_origins"] == [
        "https://dashboard.example.com",
        "http://localhost:5173",
    ]
    assert replace(settings, environment="prod").dashboard()["auth"][
        "allowed_origins"
    ] == ["https://dashboard.example.com"]
    assert replace(settings, dashboard_origin="http://localhost:5173").dashboard()[
        "auth"
    ]["allowed_origins"] == ["http://localhost:5173"]
