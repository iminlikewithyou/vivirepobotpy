import discord, time, threading, os
import github as gh
from dotenv import load_dotenv
from discord import app_commands
from datetime import datetime as dt, timedelta as td, timezone as tz

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
client.run(token=token)

# Action queue

action_queue = []
proposals = []

# Utility

def is_older_than(time: dt, diff_seconds):
    return (dt.now(time.tzinfo) - time) > td(seconds=diff_seconds)

def update_proposals():
    global proposals
    proposals = [pull for pull in base_repo.get_pulls(state="open")]

update_proposals()

# Commands

@client.tree.command(name="new_proposal", description="Creates a new change proposal", guild=DISCORD_SERVER)
async def create_proposal(inter: discord.Interaction, diff: discord.Attachment, name: str = None):
    if not is_older_than(inter.user.created_at, 259_200): # 3 days
        await inter.response.send_message("Your account is too young, come back later", ephemeral=True)
        return
    name = str(inter.user.id) + inter.created_at.astimezone(tz.utc).strftime("--%d-%m-%y-%H-%M-%S") + "--" + (name or "unnamed") #730660371844825149--00-00-00-00-00-00--unnamed or --<name>
    action_queue.append({"type":"new", "name":name, "author":inter.user.name, "data":(await diff.read()).decode("utf-8")})
    await inter.response.send_message("Creating proposal...", ephemeral=True)
    return

@client.tree.command(name="edit_proposal", description="Edit an existing proposal", guild=DISCORD_SERVER)
async def edit_proposal(inter: discord.Interaction, proposal: str, diff: discord.Attachment):
    if not is_older_than(inter.user.created_at, 259_200): # 3 days
        await inter.response.send_message("Your account is too young, come back later", ephemeral=True)
        return
    action_queue.append({"type":"edit", "name":proposal, "author":inter.user.name, "data":(await diff.read()).decode("utf-8")})
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

# Functions

def new_pullreq(task: dict):
    branch = head_repo.create_git_ref(
        f"refs/heads/{task['name']}",
        head_repo.get_branch("master").commit.sha
    ) # create the branch

    head_repo.create_file(
        path=f"changes/{task['name']}.diff",
        message="Create .diff",
        content=task["data"],
        branch=task["name"]
    ) 

    base_repo.create_pull(
        title=f"'{task['name'].split('--')[2]}' created by {task["author"]}",
        body="idk what to put here",
        base="master",
        head=f"{head_repo_author}:{task['name']}",
        maintainer_can_modify=True
    )

    update_proposals()

def edit_pullreq(task: dict):
    file = head_repo.get_contents(f"changes/{task['name']}.diff", ref=task["name"])
    head_repo.update_file(
        path=file.path,
        message="Update .diff",
        content=task["data"],
        branch=task["name"],
        sha=file.sha
    )

def run_actions():
    while True:
        if len(action_queue) > 0:
            task = action_queue.pop(0)
            if task["type"] == "new":
                new_pullreq(task)
            elif task["type"] == "edit":
                edit_pullreq(task)
            time.sleep(90) # 90s wait time
        else:
            time.sleep(10) # 90s has elapsed, so check every 10s instead

actions = threading.Thread(target=run_actions, daemon=True)
actions.start() #run in the background
