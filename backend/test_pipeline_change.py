import os
import unittest

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import DealChecklist, DealDocument, User
from app.routers.deals import change_deal_pipeline, create_deal, get_checklist, get_documents
from app.schemas import DealCreate, DealPipelineChange
from app.seed import seed_reference


class PipelineChangeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = SessionLocal()
        await seed_reference(self.db)
        self.user = User(
            email="tester",
            full_name="Tester",
            role="admin",
            password_hash="unused",
        )
        self.db.add(self.user)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def test_pipeline_change_preserves_inactive_type_data(self):
        created = await create_deal(
            DealCreate(title="Test deal", pipeline="import"), self.db, self.user
        )
        checklist = (
            await self.db.execute(
                select(DealChecklist)
                .where(DealChecklist.deal_id == created.id)
                .order_by(DealChecklist.id)
            )
        ).scalars().all()
        documents = (
            await self.db.execute(
                select(DealDocument)
                .where(DealDocument.deal_id == created.id)
                .order_by(DealDocument.id)
            )
        ).scalars().all()
        checklist[0].is_done = True
        documents[0].is_received = True
        documents[0].number = "DOC-1"
        await self.db.commit()

        local = await change_deal_pipeline(
            created.id, DealPipelineChange(pipeline="local"), self.db, self.user
        )
        self.assertEqual((local.pipeline, local.stage_id), ("local", 101))
        self.assertTrue(local.code.startswith("МП-"))
        self.assertEqual(await get_checklist(created.id, self.db, self.user), [])
        self.assertEqual(len(await get_documents(created.id, self.db, self.user)), 6)

        restored = await change_deal_pipeline(
            created.id, DealPipelineChange(pipeline="import"), self.db, self.user
        )
        self.assertEqual((restored.pipeline, restored.stage_id), ("import", 1))
        restored_checklist = await get_checklist(created.id, self.db, self.user)
        restored_documents = await get_documents(created.id, self.db, self.user)
        self.assertTrue(restored_checklist[0].is_done)
        self.assertEqual(restored_documents[0].number, "DOC-1")


if __name__ == "__main__":
    unittest.main()
