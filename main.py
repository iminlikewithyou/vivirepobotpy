import discord, os
import github as gh
from dotenv import load_dotenv
from discord import app_commands
from datetime import datetime, timedelta
from task_queue import TaskQueue

# Load environment variables

load_dotenv()

server_id = os.getenv("SERVER_ID")
token = os.getenv("DISCORD_TOKEN")
ghtoken = os.getenv("GITHUB_TOKEN")

repo_name = "vivi"
base_repo_author = os.getenv("BASE_REPO")
head_repo_author = os.getenv("HEAD_REPO")

# Set up the GitHub API

gh_api = gh.Github(auth=gh.Auth.Token(ghtoken))

base_repo = gh_api.get_repo(f"{base_repo_author}/{repo_name}")
head_repo = gh_api.get_repo(f"{head_repo_author}/{repo_name}")

# Set up the Discord bot

DISCORD_SERVER = discord.Object(id = int(server_id))

intents = discord.Intents.default()
intents.members = True

class BotClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.sync = False
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        await self.wait_until_ready()
        if not self.sync:
            self.sync = True
            await self.tree.sync(guild=DISCORD_SERVER)
        print("Bot ready, listening for commands!")

client = BotClient()

# Task queue

task_queue = TaskQueue(task_delay=90)

# Utility

def is_older_than(time: datetime, diff_seconds):
    return (datetime.now(time.tzinfo) - time) > timedelta(seconds=diff_seconds)

def update_proposals():
    global proposals
    proposals = [pull for pull in base_repo.get_pulls(state="open")]

update_proposals()

# Commands

proposalGroup = app_commands.Group(name="proposal", description="Make a proposal", guild_ids=[DISCORD_SERVER])

@proposalGroup.command(name="create", description="Create a new proposal")
async def propose_changes(inter: discord.Interaction, diff: discord.Attachment, name: str = None):
    if not is_older_than(inter.user.created_at, 259_200): # 3 days
        await inter.response.send_message("Your account is too young, come back later", ephemeral=True)
        return
    name = str(inter.user.id) + inter.created_at.strftime("--%d-%m-%y-%H-%M-%S") + "--" + (name or "unnamed") #730660371844825149--00-00-00-00-00-00--unnamed or --<name>
    task_queue.add(new_pull, name=name, author=inter.user.name, data=(await diff.read()).decode("utf-8"))
    await inter.response.send_message("Creating proposal...", ephemeral=True)
    return

@proposalGroup.command(name="edit", description="Edit an existing proposal")
async def edit_proposal(inter: discord.Interaction, proposal: str, diff: discord.Attachment):
    if not is_older_than(inter.user.created_at, 259_200): # 3 days
        await inter.response.send_message("Your account is too young, come back later", ephemeral=True)
        return
    task_queue.add(edit_pull, name=proposal, data=(await diff.read()).decode("utf-8"))
    await inter.response.send_message("Editing Proposal...", ephemeral=True)
    return

@edit_proposal.autocomplete(name="proposal")
async def proposal_auto(inter: discord.Interaction, current: str):
    ret = []
    for prop in proposals:
        if "--" in prop.head.ref and current.lower() in prop.head.ref.lower():
            ret.append(app_commands.Choice(
                name=f"{prop.head.ref.split('--')[2]} by {client.get_user(int(prop.head.ref.split('--')[0]))} at {prop.head.ref.split('--')[1].replace("-", "/", 2).replace("-", " ", 1).replace("-", ":")}", 
                value=prop.head.ref
            ))
    return ret[:25]

client.tree.add_command(proposalGroup, guild=DISCORD_SERVER)

# Functions

def new_pull(name: str, author: str, data: str):
    # Create the branch
    head_repo.create_git_ref(
        f"refs/heads/{name}",
        head_repo.get_branch("master").commit.sha
    )

    # Create the diff file
    head_repo.create_file(
        path=f"changes/{name}.diff",
        message="Create .diff",
        content=data,
        branch=name
    ) 

    # Create the pull request
    base_repo.create_pull(
        title=f"'{name.split('--')[2]}' created by {author}",
        base="master",
        head=f"{head_repo_author}:{name}",
        maintainer_can_modify=True
    )

    update_proposals()

def edit_pull(name: str, data: str):
    # Retrieve the diff file
    file = head_repo.get_contents(f"changes/{name}.diff", ref=name)

    # Update the diff file
    head_repo.update_file(
        path=file.path,
        message="Update .diff",
        content=data,
        branch=name,
        sha=file.sha
    )

#Pretty sure this needs to go at the bottom
client.run(token=token)
