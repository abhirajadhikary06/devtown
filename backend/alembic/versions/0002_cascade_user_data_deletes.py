"""cascade dependent data when users or cities are deleted

Revision ID: 0002
Revises: 0001
"""
from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    _replace_fk("cities", "cities_user_id_fkey", "users", "user_id")
    _replace_fk("snapshots", "snapshots_user_id_fkey", "users", "user_id")
    _replace_fk("ledger", "ledger_user_id_fkey", "users", "user_id")
    _replace_fk("banners", "banners_city_id_fkey", "cities", "city_id")


def downgrade():
    for table, constraint, parent, column in (
        ("banners", "banners_city_id_fkey", "cities", "city_id"),
        ("ledger", "ledger_user_id_fkey", "users", "user_id"),
        ("snapshots", "snapshots_user_id_fkey", "users", "user_id"),
        ("cities", "cities_user_id_fkey", "users", "user_id"),
    ):
        naming_convention = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}
        with op.batch_alter_table(table, naming_convention=naming_convention) as batch:
            batch.drop_constraint(constraint, type_="foreignkey")
            batch.create_foreign_key(constraint, parent, [column], ["id"])


def _replace_fk(table, constraint, parent, column):
    naming_convention = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}
    with op.batch_alter_table(table, naming_convention=naming_convention) as batch:
        batch.drop_constraint(constraint, type_="foreignkey")
        batch.create_foreign_key(constraint, parent, [column], ["id"], ondelete="CASCADE")
