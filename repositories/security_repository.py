"""All database access for antinuke and honeypot."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.security_models import (
    AntinukeAdmin,
    AntinukeConfig,
    AntinukeModule,
    AntinukeWhitelist,
    FakePermission,
    HoneypotConfig,
)


async def get_or_create_antinuke_config(session: AsyncSession, guild_id: int) -> AntinukeConfig:
    result = await session.execute(select(AntinukeConfig).where(AntinukeConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = AntinukeConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def is_whitelisted(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(AntinukeWhitelist).where(
            AntinukeWhitelist.guild_id == guild_id, AntinukeWhitelist.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def add_whitelist(session: AsyncSession, guild_id: int, user_id: int) -> None:
    if await is_whitelisted(session, guild_id, user_id):
        return
    session.add(AntinukeWhitelist(guild_id=guild_id, user_id=user_id))
    await session.commit()


async def remove_whitelist(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(AntinukeWhitelist).where(
            AntinukeWhitelist.guild_id == guild_id, AntinukeWhitelist.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_or_create_honeypot_config(session: AsyncSession, guild_id: int) -> HoneypotConfig:
    result = await session.execute(select(HoneypotConfig).where(HoneypotConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = HoneypotConfig(guild_id=guild_id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


async def update_honeypot_config(session: AsyncSession, cfg: HoneypotConfig, **fields) -> HoneypotConfig:
    for key, value in fields.items():
        setattr(cfg, key, value)
    await session.commit()
    await session.refresh(cfg)
    return cfg


async def increment_honeypot_caught(session: AsyncSession, guild_id: int) -> int:
    cfg = await get_or_create_honeypot_config(session, guild_id)
    cfg.caught_count += 1
    await session.commit()
    await session.refresh(cfg)
    return cfg.caught_count


async def delete_honeypot_config(session: AsyncSession, guild_id: int) -> bool:
    result = await session.execute(select(HoneypotConfig).where(HoneypotConfig.guild_id == guild_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return False
    await session.delete(cfg)
    await session.commit()
    return True


# ---------------------------------------------------------- antinuke admins

async def is_antinuke_admin(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(AntinukeAdmin).where(AntinukeAdmin.guild_id == guild_id, AntinukeAdmin.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


async def add_antinuke_admin(session: AsyncSession, guild_id: int, user_id: int) -> None:
    if await is_antinuke_admin(session, guild_id, user_id):
        return
    session.add(AntinukeAdmin(guild_id=guild_id, user_id=user_id))
    await session.commit()


async def remove_antinuke_admin(session: AsyncSession, guild_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(AntinukeAdmin).where(AntinukeAdmin.guild_id == guild_id, AntinukeAdmin.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_antinuke_admins(session: AsyncSession, guild_id: int) -> list[int]:
    result = await session.execute(select(AntinukeAdmin.user_id).where(AntinukeAdmin.guild_id == guild_id))
    return [row[0] for row in result.all()]


# ---------------------------------------------------------- antinuke modules

async def get_or_create_module(session: AsyncSession, guild_id: int, module_name: str) -> AntinukeModule:
    result = await session.execute(
        select(AntinukeModule).where(
            AntinukeModule.guild_id == guild_id, AntinukeModule.module_name == module_name
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AntinukeModule(guild_id=guild_id, module_name=module_name)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def update_module(session: AsyncSession, module: AntinukeModule, **fields) -> AntinukeModule:
    for key, value in fields.items():
        setattr(module, key, value)
    await session.commit()
    await session.refresh(module)
    return module


async def get_all_modules(session: AsyncSession, guild_id: int) -> dict[str, AntinukeModule]:
    result = await session.execute(select(AntinukeModule).where(AntinukeModule.guild_id == guild_id))
    return {row.module_name: row for row in result.scalars().all()}


# ---------------------------------------------------------- fake permissions

async def add_fake_permission(session: AsyncSession, guild_id: int, role_id: int, permission: str) -> bool:
    result = await session.execute(
        select(FakePermission).where(
            FakePermission.guild_id == guild_id,
            FakePermission.role_id == role_id,
            FakePermission.permission == permission,
        )
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(FakePermission(guild_id=guild_id, role_id=role_id, permission=permission))
    await session.commit()
    return True


async def remove_fake_permission(session: AsyncSession, guild_id: int, role_id: int, permission: str) -> bool:
    result = await session.execute(
        select(FakePermission).where(
            FakePermission.guild_id == guild_id,
            FakePermission.role_id == role_id,
            FakePermission.permission == permission,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_fake_permissions_for_role(session: AsyncSession, guild_id: int, role_id: int) -> list[str]:
    result = await session.execute(
        select(FakePermission.permission).where(
            FakePermission.guild_id == guild_id, FakePermission.role_id == role_id
        )
    )
    return sorted(row[0] for row in result.all())


async def get_all_fake_permissions(session: AsyncSession, guild_id: int) -> list[FakePermission]:
    result = await session.execute(select(FakePermission).where(FakePermission.guild_id == guild_id))
    return list(result.scalars().all())


async def has_fake_permission(session: AsyncSession, guild_id: int, role_ids: list[int], permission: str) -> bool:
    if not role_ids:
        return False
    result = await session.execute(
        select(FakePermission).where(
            FakePermission.guild_id == guild_id,
            FakePermission.role_id.in_(role_ids),
            FakePermission.permission == permission,
        )
    )
    return result.first() is not None


async def reset_fake_permissions(session: AsyncSession, guild_id: int) -> None:
    await session.execute(FakePermission.__table__.delete().where(FakePermission.guild_id == guild_id))
    await session.commit()