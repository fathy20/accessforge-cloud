import unittest

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, MetaData, String, Table, UniqueConstraint

from backend.database import Base, NAMING_CONVENTION
import backend.models  # noqa: F401


class TestMetadataNaming(unittest.TestCase):
    def test_current_model_constraints_use_deterministic_names(self):
        users = Base.metadata.tables["users"]
        user_roles = Base.metadata.tables["user_roles"]
        email_index = next(index for index in users.indexes if index.name == "ix_users_email")

        self.assertEqual(users.primary_key.name, "pk_users")
        self.assertEqual(next(iter(user_roles.foreign_keys)).constraint.name, "fk_user_roles_user_id_users")
        self.assertEqual(email_index.name, "ix_users_email")
        self.assertTrue(email_index.unique)

    def test_temporary_check_constraint_uses_convention(self):
        metadata = MetaData(naming_convention=NAMING_CONVENTION)
        status = Column("status", String(16))
        Table(
            "naming_example",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("email", String(255), unique=True),
            status,
            CheckConstraint(status.in_(["active", "inactive"])),
            Column("parent_id", Integer, ForeignKey("naming_example.id")),
        )

        table = metadata.tables["naming_example"]
        check = next(constraint for constraint in table.constraints if isinstance(constraint, CheckConstraint))
        unique = next(constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint))
        foreign_key = next(iter(table.foreign_keys))

        self.assertEqual(table.primary_key.name, "pk_naming_example")
        self.assertEqual(unique.name, "uq_naming_example_email")
        self.assertEqual(check.name, "ck_naming_example_status")
        self.assertEqual(foreign_key.constraint.name, "fk_naming_example_parent_id_naming_example")


if __name__ == "__main__":
    unittest.main()