"""02: Pass one ADK SkillToolset plus ordinary tools.

The same `tools` argument can also receive ADK BaseTool and BaseToolset values,
including McpToolset instances.
"""

from adk_agent_harness import create_deep_agent
from google.adk.skills import models
from google.adk.tools import skill_toolset


def get_project_status(project: str) -> str:
    """Return a short project status."""

    return f"{project}: no status backend configured."


status_skill = models.Skill(
    frontmatter=models.Frontmatter(
        name="status-skill",
        description="Summarize project status using available project tools.",
    ),
    instructions="Use project status tools and return a concise summary.",
)

project_skills = skill_toolset.SkillToolset(skills=[status_skill])

app = create_deep_agent(
    name="skilled_deep_agent",
    model_client="gemini-3-flash-preview",
    instruction="Use skills when they are relevant.",
    tools=[get_project_status],
    skills=project_skills,
)


if __name__ == "__main__":
    print(app)

