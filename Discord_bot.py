import os
import time
import json
import asyncio
import tempfile
from collections import defaultdict

import discord
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ui import Button, View
from dotenv import load_dotenv
import pandas as pd
import requests

# Load environment variables from .env file
load_dotenv()

# Retrieve the Discord token and other tokens from the environment
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BEAR_TOKEN = os.getenv('BEAR_TOKEN')
DW_TOKEN = os.getenv('DW_TOKEN')

if DISCORD_TOKEN is None:
    raise ValueError("Discord token not found. Please check your .env file.")

# Set up intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Function to validate EPIC Account ID
def is_valid_epic_id(epic_id):
    return len(epic_id) == 32 and epic_id.isalnum()

# JSON file path for storing user EPIC IDs
epic_ids_file = 'epic_ids.json'

# Load the user_epic_ids from a JSON file
def load_epic_ids():
    try:
        with open(epic_ids_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save the user_epic_ids to a JSON file
def save_epic_ids():
    with open(epic_ids_file, 'w') as f:
        json.dump(user_epic_ids, f)

# Load existing data when the bot starts
user_epic_ids = load_epic_ids()

# Admin role name
admin_role_name = "Admin"

# Function to check if the user has the Admin role
def is_admin(interaction: discord.Interaction):
    admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
    return admin_role in interaction.user.roles

# Cooldown dictionary
cooldowns = defaultdict(lambda: 0)

# Common messages used throughout the bot
DM_REASON = "To protect your privacy and prevent potential attacks on your account, please check your DMs to provide your EPIC Account ID."
PROVIDE_EPIC_ID_MSG = "Please provide your EPIC Account ID within 60 seconds:"
INVALID_EPIC_ID_MSG = "The provided EPIC Account ID is invalid. Please ensure it is a 32 character alphanumeric string."
ID_IN_USE_MSG = "The provided EPIC Account ID is already in use. Please provide a different ID."
THANK_YOU_MSG = "Thank you! Your EPIC Account ID has been saved."
TOOK_TOO_LONG_MSG = "You took too long to respond. Please try again."
EPIC_ID_SET_MSG = "Click the button below to set your EPIC Account ID."
EPIC_ID_EDIT_MSG = "Click the button below to edit your EPIC Account ID."
COOLDOWN_TIME = 10  # Cooldown time in seconds

# Function to make an API call to retrieve the wallet using the EPIC ID
def get_wallet_by_epic_id(epic_id):
    wallet_api_url = f"https://api.staging.deverse.world/api/authenticate/{epic_id}"
    wallet_headers = {"x-dw-api-key": f"{DW_TOKEN}"}
    
    try:
        wallet_response = requests.get(wallet_api_url, headers=wallet_headers)
        if wallet_response.status_code in [200, 201]:
            wallet_data = wallet_response.json().get('data', {})
            id_wallet = wallet_data.get('thx', {}).get('id_wallet')
            if id_wallet:
                return id_wallet, None  # Successfully retrieved the wallet
            else:
                return None, "'id_wallet' not found in the response data."  # Handle the case where 'id_wallet' is missing
        else:
            return None, f"API responded with status code: {wallet_response.status_code}. Response: {wallet_response.text}"
    except Exception as e:
        return None, str(e)  # Return None for id_wallet and the exception as an error message

# Function to retrieve the balance of a wallet using its id_wallet
def get_wallet_balance(id_wallet):
    balance_api_url = f"https://api.helpers.testnet.thxnet.org/rest/v0.5/id_wallet/{id_wallet}/testnet_leafchain_aether/fts"
    balance_headers = {"Authorization": f"Bearer {BEAR_TOKEN}"}
    
    try:
        balance_response = requests.get(balance_api_url, headers=balance_headers)
        if balance_response.status_code == 200:
            balance_data = balance_response.json().get('result', {})
            return balance_data, None
        else:
            return None, f"API responded with status code: {balance_response.status_code}."
    except Exception as e:
        return None, str(e)

# Function to transfer resources to a wallet
def transfer_resource(id_wallet, points, asset_id):
    transfer_api_url = "https://api.helpers.testnet.thxnet.org/rest/v0.5/me/testnet_leafchain_aether/ft/transfer"
    transfer_payload = {
        "receiver_id_wallet_address": id_wallet,
        "transfer_value_human": points,
        "native": False,
        "asset_id": asset_id
    }
    transfer_headers = {"Authorization": f"Bearer {BEAR_TOKEN}"}
    
    try:
        transfer_response = requests.post(transfer_api_url, headers=transfer_headers, json=transfer_payload)
        if transfer_response.status_code == 200:
            return True, None
        else:
            return False, f"API responded with status code: {transfer_response.status_code}."
    except Exception as e:
        return False, str(e)

# Event triggered when the bot is ready
@bot.event
async def on_ready():
    await bot.tree.sync(guild=None)
    print(f'We have logged in as {bot.user} and synced the commands.')

# Create a command group
class DwCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="dw-commands", description="Commands for managing EPIC IDs and game info")

    # Command to set the EPIC Account ID
    @app_commands.command(name="set", description="Set your EPIC Account ID")
    async def dw_set(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Callback function for the button to set EPIC Account ID
        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return

            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME

            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return

            if user_id in user_epic_ids:
                await button_interaction.response.send_message("You already have an EPIC Account ID set. You cannot set it again.", ephemeral=True)
                return

            await button_interaction.response.send_message(DM_REASON, ephemeral=True)

            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)

            try:
                await button_interaction.user.send(PROVIDE_EPIC_ID_MSG)
                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)
                    epic_id = msg.content

                    if is_valid_epic_id(epic_id):
                        if epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)
                        else:
                            user_epic_ids[user_id] = epic_id
                            save_epic_ids()
                            await button_interaction.user.send(THANK_YOU_MSG)
                            await button_interaction.followup.send('Setup completed successfully!', ephemeral=True)
                            await interaction.channel.send(f'{button_interaction.user.mention} has successfully set their EPIC Account ID.')
                            await interaction.delete_original_response()
                            break
                    else:
                        await button_interaction.user.send(INVALID_EPIC_ID_MSG)
            except asyncio.TimeoutError:
                await button_interaction.user.send(TOOK_TOO_LONG_MSG)
                await button_interaction.followup.send(TOOK_TOO_LONG_MSG, ephemeral=True)
                await interaction.delete_original_response()

            set_button.disabled = True
            view.clear_items()
            try:
                await button_interaction.message.edit(view=view)
            except discord.errors.NotFound:
                pass

        set_button = Button(label="Set EPIC Account ID", style=discord.ButtonStyle.primary)
        set_button.callback = button_callback

        help_button = Button(label="Help", style=discord.ButtonStyle.link, url="https://www.epicgames.com/help/en-US/c-Category_EpicAccount/c-AccountSecurity/what-is-an-epic-account-id-and-where-can-i-find-it-a000084674")

        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)

        close_button = Button(label="Close", style=discord.ButtonStyle.danger)
        close_button.callback = close_button_callback

        view = View()
        view.add_item(set_button)
        view.add_item(help_button)
        view.add_item(close_button)

        await interaction.response.send_message(EPIC_ID_SET_MSG, view=view, ephemeral=True)

    # Command to view the EPIC Account ID
    @app_commands.command(name="view", description="View your EPIC Account ID and balance")
    async def dw_view(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        epic_id = user_epic_ids.get(user_id)
        if not epic_id:
            await interaction.response.send_message('You have not provided an EPIC Account ID yet.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        id_wallet, error = get_wallet_by_epic_id(epic_id)
        if not id_wallet:
            await interaction.followup.send(f"Failed to retrieve wallet. {error}", ephemeral=True)
            return

        balance_data, error = get_wallet_balance(id_wallet)
        if error:
            await interaction.followup.send(f"Failed to retrieve balance. {error}", ephemeral=True)
            return

        dp_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 1), 0)
        oil_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 2), 0)
        energy_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 3), 0)

        embed = discord.Embed(title="Your Account Information", color=discord.Color.blue())
        embed.add_field(name="Discord Name", value=interaction.user.name, inline=True)
        embed.add_field(name="EPIC Account ID", value=epic_id, inline=True)
        embed.add_field(name="Wallet ID", value=f"{id_wallet}", inline=False)
        embed.add_field(name="DP", value=f"{dp_balance}", inline=True)
        embed.add_field(name="Oil", value=f"{oil_balance}", inline=True)
        embed.add_field(name="Energy", value=f"{energy_balance}", inline=True)
        embed.set_thumbnail(url=interaction.user.avatar.url)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # Command to edit the EPIC Account ID
    @app_commands.command(name="edit", description="Edit your EPIC Account ID")
    async def dw_edit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return

            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME

            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return

            if user_id not in user_epic_ids:
                await button_interaction.response.send_message("You do not have an EPIC Account ID set yet. Please set it first using the /dw set command.", ephemeral=True)
                return

            await button_interaction.response.send_message(DM_REASON, ephemeral=True)

            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)

            try:
                await button_interaction.user.send("Please provide your new EPIC Account ID within 60 seconds:")
                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)
                    new_epic_id = msg.content

                    if is_valid_epic_id(new_epic_id):
                        if new_epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)
                        else:
                            user_epic_ids[user_id] = new_epic_id
                            save_epic_ids()
                            await button_interaction.user.send('Thank you! Your EPIC Account ID has been updated.')
                            await button_interaction.followup.send('Update completed successfully!', ephemeral=True)
                            await interaction.channel.send(f'{button_interaction.user.mention} has successfully updated their EPIC Account ID.')
                            await interaction.delete_original_response()
                            break
                    else:
                        await button_interaction.user.send(INVALID_EPIC_ID_MSG)
            except asyncio.TimeoutError:
                await button_interaction.user.send(TOOK_TOO_LONG_MSG)
                await button_interaction.followup.send(TOOK_TOO_LONG_MSG, ephemeral=True)
                await interaction.delete_original_response()

            button.disabled = True
            view.clear_items()
            try:
                await button_interaction.message.edit(view=view)
            except discord.errors.NotFound:
                pass

        button = Button(label="Edit EPIC Account ID", style=discord.ButtonStyle.primary)
        button.callback = button_callback

        view = View()
        view.add_item(button)

        await interaction.response.send_message(EPIC_ID_EDIT_MSG, view=view, ephemeral=True)

    # Command to list all EPIC Account IDs (Admin only)
    @app_commands.command(name="list", description="List all EPIC Account IDs (Admin only)")
    async def dw_list(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You do not have the necessary permissions to use this command.", ephemeral=True)
            return

        if user_epic_ids:
            embed = discord.Embed(title="List of EPIC Account IDs", color=discord.Color.green())
            data_list = []

            for user_id, epic_id in user_epic_ids.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else f"User ID: {user_id}"
                embed.add_field(name=username, value=epic_id, inline=False)
                data_list.append({'EpicID': epic_id, 'Points': 0, 'OilPoints': 0, 'EnergyPoints': 0})

            export_button = Button(label="Export to CSV", style=discord.ButtonStyle.primary)

            async def export_button_callback(button_interaction):
                df = pd.DataFrame(data_list)
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                        temp_file_path = tmp_file.name
                        df.to_csv(temp_file_path, index=False)

                    await button_interaction.response.send_message(file=discord.File(temp_file_path, filename="epic_ids_list.csv"), ephemeral=True)
                finally:
                    os.remove(temp_file_path)

            export_button.callback = export_button_callback

            close_button = Button(label="Close", style=discord.ButtonStyle.danger)

            async def close_button_callback(button_interaction):
                try:
                    await interaction.delete_original_response()
                except discord.errors.NotFound:
                    await button_interaction.response.send_message("Message already deleted.", ephemeral=True)

            close_button.callback = close_button_callback

            view = View()
            view.add_item(export_button)
            view.add_item(close_button)

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message("No EPIC Account IDs have been set yet.", ephemeral=True)

    # Command to distribute DP based on a CSV file (Admin only)
    @app_commands.command(name="distribute", description="Distribute DP, Oil, and Energy based on a CSV file (Admin only)")
    async def dw_distribute(self, interaction: Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        if not is_admin(interaction):
            await interaction.followup.send("You do not have the necessary permissions to use this command.", ephemeral=True)
            return

        if user_epic_ids:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                temp_file_path = tmp_file.name

            await file.save(fp=temp_file_path)

            data = pd.read_csv(temp_file_path)
            data.columns = data.columns.str.strip()

            required_columns = {"EpicID", "Points", "OilPoints", "EnergyPoints"}
            if not required_columns.issubset(data.columns):
                await interaction.followup.send("The CSV file must contain 'EpicID', 'Points', 'OilPoints', and 'EnergyPoints' columns.", ephemeral=True)
                return

            data['EpicID'] = data['EpicID'].str.strip().str.lower()
            normalized_user_epic_ids = {k: v.strip().lower() for k, v in user_epic_ids.items()}

            bot_balance_data, error = get_wallet_balance("5DSFYPkB2b6auEwZxqbkAWa213EbBfDtRuaRrnivA3RvoMyg")
            if error or not bot_balance_data:
                await interaction.followup.send(f"Failed to check Bot Bank Account balance. {error}", ephemeral=True)
                return

            dp_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 1), 0)
            oil_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 2), 0)
            energy_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 3), 0)

            if dp_balance <= 0 or oil_balance <= 0 or energy_balance <= 0:
                await interaction.followup.send("Insufficient balance in the Bot Bank Account for one or more resources.", ephemeral=True)
                return

            results = []

            for _, row in data.iterrows():
                epic_id = row['EpicID']
                dp_points = row['Points']
                oil_points = row['OilPoints']
                energy_points = row['EnergyPoints']

                if dp_points > dp_balance or oil_points > oil_balance or energy_points > energy_balance:
                    results.append(f"Not enough resources to distribute to {epic_id}.")
                    continue

                user_id = {v: k for k, v in normalized_user_epic_ids.items()}.get(epic_id)

                if user_id:
                    id_wallet, error = get_wallet_by_epic_id(epic_id)
                    if error or not id_wallet:
                        results.append(f"Failed to retrieve wallet for Epic ID {epic_id}. {error}")
                        continue

                    for resource_name, points, asset_id in [("DP", dp_points, 1), ("Oil", oil_points, 2), ("Energy", energy_points, 3)]:
                        if points > 0:
                            success, error = transfer_resource(id_wallet, points, asset_id)
                            if success:
                                results.append(f"Successfully distributed {points} {resource_name} to {epic_id} (User: {user_id}).")
                            else:
                                results.append(f"Failed to distribute {points} {resource_name} to {epic_id}. {error}")

                else:
                    results.append(f"User with Epic ID {epic_id} not found in the server.")

            result_message = "\n".join(results)
            await interaction.followup.send(f"Distribution process completed:\n{result_message}", ephemeral=True)
        else:
            await interaction.followup.send("No EPIC Account IDs have been set yet.", ephemeral=True)


# Register the command group with the bot
bot.tree.add_command(DwCommands())

# Run the bot with your token
bot.run(DISCORD_TOKEN)
