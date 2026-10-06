"""Scoped execution agents: the supervisor plans; specialists own tool allowlists.
No extra LLM calls for simple execution. This keeps delegation auditable and bounded.
"""

from app.tools.schemas import GROUPS


class Specialist:
    def __init__(self, name, router):
        self.name = name
        self.router = router

    async def execute(self, tool, args, user, run_id):
        if tool not in GROUPS[self.name]:
            raise ValueError("Tool outside specialist scope")
        return await self.router.call(tool, args, user, run_id)
