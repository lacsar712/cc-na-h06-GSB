from .settings import *  # noqa: F401,F403

# 本地/CI 测试使用内存 SQLite，不依赖 PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
