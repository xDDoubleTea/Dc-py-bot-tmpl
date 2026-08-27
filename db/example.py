from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    """A minimal example model: one row per Discord user (see cogs/general.py)."""

    __tablename__ = "users"

    # Discord snowflakes exceed 32 bits, so store them as BIGINT rather than the
    # INTEGER that Mapped[int] would pick by default on other dialects.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name})"


class GuildSetting(Base):
    """
    One configuration value for one guild (see cogs/settings.py).

    The primary key is the (guild_id, key) pair: it scopes every row to a single
    guild, keeps a guild from holding two values for the same key, and gives the
    upsert in `/settings set` something to detect a conflict on.
    """

    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Values are stored as text; IDs (channels, roles) are stored as str(obj.id) and
    # resolved back into Discord objects on read.
    value: Mapped[str] = mapped_column(String(512))

    def __repr__(self) -> str:
        return f"GuildSetting(guild_id={self.guild_id}, key={self.key}, value={self.value})"
