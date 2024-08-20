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
import requests  # Import the requests library to make API calls

# Load environment variables from .env file
load_dotenv()

# Retrieve the Discord token from the environment
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BEAR_TOKEN = os.getenv('BEAR_TOKEN')
DW_TOKEN = os.getenv('DW_TOKEN')
HOST_URL = os.getenv('HOST_URL')  # Add this to your .env file for API endpoint

# Debug print to verify if the token is loaded
print(f"Token loaded: {DISCORD_TOKEN}")

# Raise an error if the token is not found
if DISCORD_TOKEN is None:
    raise ValueError("Discord token not found. Please check your .env file.")

# Set up intents to receive messages and message content
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True  # Ensure we have access to guild information

# Initialize the bot with a command prefix and intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Function to validate EPIC Account ID (32 character alphanumeric string)
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
admin_role_name = "Admin"  # Change this to your admin role name

# Function to check if the user has the Admin role
def is_admin(interaction: discord.Interaction):
    admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
    return admin_role in interaction.user.roles

# Cooldown dictionary to prevent spamming
cooldowns = defaultdict(lambda: 0)

# Common messages used throughout the bot
DM_REASON = "To protect your privacy and prevent potential attacks on your account, please check your DMs to provide your EPIC Account ID."
CHECK_DM_MSG = "Please check your DMs to provide your EPIC Account ID."
PROVIDE_EPIC_ID_MSG = "Please provide your EPIC Account ID within 60 seconds:"
INVALID_EPIC_ID_MSG = "The provided EPIC Account ID is invalid. Please ensure it is a 32 character alphanumeric string."
ID_IN_USE_MSG = "The provided EPIC Account ID is already in use. Please provide a different ID."
THANK_YOU_MSG = "Thank you! Your EPIC Account ID has been saved."
TOOK_TOO_LONG_MSG = "You took too long to respond. Please try again."
EPIC_ID_SET_MSG = "Click the button below to set your EPIC Account ID. You will receive further instructions in your DMs to protect your privacy and prevent potential attacks."
EPIC_ID_EDIT_MSG = "Click the button below to edit your EPIC Account ID. You will receive further instructions in your DMs to protect your privacy and prevent potential attacks."
EPIC_ID_VIEW_MSG = "Click the button below to view your EPIC Account ID."

COOLDOWN_TIME = 10  # Cooldown time in seconds

# Event triggered when the bot is ready
@bot.event
async def on_ready():
    await bot.tree.sync(guild=None)  # Syncing globally
    print(f'We have logged in as {bot.user} and synced the commands.')

# Custom help command
@bot.tree.command(name="help", description="Shows the help menu")
async def help_command(interaction: discord.Interaction):
    help_message = """
    Here are the commands you can use:
    /dw-commands set: Set your EPIC Account ID
    /dw-commands edit: Edit your EPIC Account ID
    /dw-commands view: View your EPIC Account ID
    /dw-commands list: List all EPIC Account IDs (Admin only)
    /dw-commands gameinfo: View details about Deverse World
    /dw-commands distribute: Distribute DP based on CSV file (Admin only)
    """
    await interaction.response.send_message(help_message, ephemeral=True)

# Create a command group
class DwCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="dw-commands", description="Commands for managing EPIC IDs and game info")

    # Command to set the EPIC Account ID
    @app_commands.command(name="set", description="Set your EPIC Account ID")
    async def dw_set(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)  # Store Discord ID as a string for JSON compatibility

        # Callback function for the button to set EPIC Account ID
        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return

            # Update the cooldown time
            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME

            # Ensure the user clicking the button is the one who initiated the command
            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return

            # Check if the user already has an EPIC ID set
            if user_id in user_epic_ids:
                await button_interaction.response.send_message("You already have an EPIC Account ID set. You cannot set it again.", ephemeral=True)
                return

            # Prompt the user to provide their EPIC ID via DM
            await button_interaction.response.send_message(DM_REASON, ephemeral=True)

            # Function to check if the message is from the user and in a DM channel
            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)

            try:
                # Prompt the user to provide their EPIC ID
                await button_interaction.user.send(PROVIDE_EPIC_ID_MSG)
                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)
                    epic_id = msg.content

                    # Validate the EPIC ID
                    if is_valid_epic_id(epic_id):
                        if epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)
                        else:
                            user_epic_ids[user_id] = epic_id
                            save_epic_ids()  # Save the updated dictionary to JSON
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

            # Disable the button and clear the view to prevent further interactions
            set_button.disabled = True
            view.clear_items()
            try:
                await button_interaction.message.edit(view=view)
            except discord.errors.NotFound:
                pass

        # Create the button to set the EPIC ID
        set_button = Button(label="Set EPIC Account ID", style=discord.ButtonStyle.primary)
        set_button.callback = button_callback

        # Help button linking to Epic's support page
        help_button = Button(label="Help", style=discord.ButtonStyle.link, url="https://www.epicgames.com/help/en-US/c-Category_EpicAccount/c-AccountSecurity/what-is-an-epic-account-id-and-where-can-i-find-it-a000084674")

        # Callback function for the close button to delete the original message
        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)

        # Create the close button
        close_button = Button(label="Close", style=discord.ButtonStyle.danger)
        close_button.callback = close_button_callback

        # Create the view (UI container) and add the buttons
        view = View()
        view.add_item(set_button)
        view.add_item(help_button)
        view.add_item(close_button)

        # Send the message with the buttons to the user
        await interaction.response.send_message(EPIC_ID_SET_MSG, view=view, ephemeral=True)

    # Command to view the EPIC Account ID
    @app_commands.command(name="view", description="View your EPIC Account ID")
    async def dw_view(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Retrieve the user's EPIC ID
        epic_id = user_epic_ids.get(user_id)
        if epic_id:
            embed = discord.Embed(title="Your Account Information", color=discord.Color.blue())
            embed.add_field(name="Discord Name", value=interaction.user.name, inline=True)
            embed.add_field(name="EPIC Account ID", value=epic_id, inline=True)
            embed.set_thumbnail(url=interaction.user.avatar.url)
        else:
            await interaction.response.send_message('You have not provided an EPIC Account ID yet.', ephemeral=True)
            return

        # Callback function for the close button
        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)

        # Create the close button
        close_button = Button(label="Close", style=discord.ButtonStyle.danger)
        close_button.callback = close_button_callback

        # Create the view (UI container) and add the button
        view = View()
        view.add_item(close_button)

        # Send the embed message with the close button to the user
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # Command to edit the EPIC Account ID
    @app_commands.command(name="edit", description="Edit your EPIC Account ID")
    async def dw_edit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        # Callback function for the button to edit EPIC Account ID
        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return

            # Update the cooldown time
            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME

            # Ensure the user clicking the button is the one who initiated the command
            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return

            # Ensure the user has an existing EPIC ID to edit
            if user_id not in user_epic_ids:
                await button_interaction.response.send_message("You do not have an EPIC Account ID set yet. Please set it first using the /dw set command.", ephemeral=True)
                return

            # Prompt the user to provide their new EPIC ID via DM
            await button_interaction.response.send_message(DM_REASON, ephemeral=True)

            # Function to check if the message is from the user and in a DM channel
            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)

            try:
                # Prompt the user to provide their new EPIC ID
                await button_interaction.user.send("Please provide your new EPIC Account ID within 60 seconds:")

                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)
                    new_epic_id = msg.content

                    # Validate the new EPIC ID
                    if is_valid_epic_id(new_epic_id):
                        if new_epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)
                        else:
                            user_epic_ids[user_id] = new_epic_id
                            save_epic_ids()  # Save the updated dictionary to JSON
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

            # Disable the button and clear the view to prevent further interactions
            button.disabled = True
            view.clear_items()
            try:
                await button_interaction.message.edit(view=view)
            except discord.errors.NotFound:
                pass

        # Create the button to edit the EPIC ID
        button = Button(label="Edit EPIC Account ID", style=discord.ButtonStyle.primary)
        button.callback = button_callback

        # Create the view (UI container) and add the button
        view = View()
        view.add_item(button)

        # Send the message with the button to the user
        await interaction.response.send_message(EPIC_ID_EDIT_MSG, view=view, ephemeral=True)

    # Command to list all EPIC Account IDs (Admin only)
    @app_commands.command(name="list", description="List all EPIC Account IDs (Admin only)")
    async def dw_list(self, interaction: discord.Interaction):
        # Check if the user has the Admin role
        if not is_admin(interaction):
            await interaction.response.send_message("You do not have the necessary permissions to use this command.", ephemeral=True)
            return

        # If EPIC IDs are available, create an embedded message with the list
        if user_epic_ids:
            embed = discord.Embed(title="List of EPIC Account IDs", color=discord.Color.green())
            data_list = []

            for user_id, epic_id in user_epic_ids.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else f"User ID: {user_id}"
                embed.add_field(name=username, value=epic_id, inline=False)
                # Prepare data for the CSV export with default values for Points, OilPoints, and EnergyPoints
                data_list.append({'EpicID': epic_id, 'Points': 0, 'OilPoints': 0, 'EnergyPoints': 0})

            # Button to export the list to a CSV file
            export_button = Button(label="Export to CSV", style=discord.ButtonStyle.primary)

            # Callback function for exporting the list to CSV
            async def export_button_callback(button_interaction):
                df = pd.DataFrame(data_list)
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                        temp_file_path = tmp_file.name
                        df.to_csv(temp_file_path, index=False)

                    # Send the CSV file as a response
                    await button_interaction.response.send_message(file=discord.File(temp_file_path, filename="epic_ids_list.csv"), ephemeral=True)
                finally:
                    # Clean up the temporary file
                    os.remove(temp_file_path)

            export_button.callback = export_button_callback

            # Button to close the message
            close_button = Button(label="Close", style=discord.ButtonStyle.danger)

            # Callback function to close the message
            async def close_button_callback(button_interaction):
                try:
                    await interaction.delete_original_response()
                except discord.errors.NotFound:
                    await button_interaction.response.send_message("Message already deleted.", ephemeral=True)

            close_button.callback = close_button_callback

            # Create the view (UI container) and add the buttons
            view = View()
            view.add_item(export_button)
            view.add_item(close_button)

            # Send the embedded message with the buttons
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message("No EPIC Account IDs have been set yet.", ephemeral=True)

    # Command to distribute DP based on a CSV file (Admin only)
    @app_commands.command(name="distribute", description="Distribute DP, Oil, and Energy based on a CSV file (Admin only)")
    async def dw_distribute(self, interaction: Interaction, file: discord.Attachment):
        # Acknowledge the interaction immediately
        await interaction.response.defer(ephemeral=True)

        # Check if the user has the Admin role
        if not is_admin(interaction):
            await interaction.followup.send("You do not have the necessary permissions to use this command.", ephemeral=True)
            return

        # If EPIC IDs are available, proceed with the distribution
        if user_epic_ids:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                temp_file_path = tmp_file.name

            # Save the uploaded file to a temporary location
            await file.save(fp=temp_file_path)

            # Load the CSV file into a DataFrame
            data = pd.read_csv(temp_file_path)
            data.columns = data.columns.str.strip()

            # Ensure the CSV has the necessary columns
            required_columns = {"EpicID", "Points", "OilPoints", "EnergyPoints"}
            if not required_columns.issubset(data.columns):
                await interaction.followup.send("The CSV file must contain 'EpicID', 'Points', 'OilPoints', and 'EnergyPoints' columns.", ephemeral=True)
                return

            # Normalize EPIC IDs for case-insensitive comparison
            data['EpicID'] = data['EpicID'].str.strip().str.lower()
            normalized_user_epic_ids = {k: v.strip().lower() for k, v in user_epic_ids.items()}

            # Step 1: Check the Bot Bank Account Balance for DP, Oil, and Energy
            balance_api_url = "https://api.helpers.testnet.thxnet.org/rest/v0.5/id_wallet/5DSFYPkB2b6auEwZxqbkAWa213EbBfDtRuaRrnivA3RvoMyg/testnet_leafchain_aether/fts"
            balance_headers = {
                "Authorization": f"Bearer {BEAR_TOKEN}"  # Replace with your actual bearer token
            }

            try:
                balance_response = requests.get(balance_api_url, headers=balance_headers)
                if balance_response.status_code == 200:
                    balance_data = balance_response.json().get('result', {})
                    dp_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 1), 0)
                    oil_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 2), 0)  # Assuming 2 is for Oil
                    energy_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 3), 0)  # Assuming 3 is for Energy

                    if dp_balance <= 0 or oil_balance <= 0 or energy_balance <= 0:
                        await interaction.followup.send("Insufficient balance in the Bot Bank Account for one or more resources.", ephemeral=True)
                        return
                else:
                    await interaction.followup.send(f"Failed to check Bot Bank Account balance. API responded with status code: {balance_response.status_code}.", ephemeral=True)
                    return
            except Exception as e:
                await interaction.followup.send(f"Failed to check Bot Bank Account balance. Error: {str(e)}", ephemeral=True)
                return

            # Initialize a list to store results for reporting
            results = []

            # Step 2: Retrieve the id_wallet using EPIC-ID and distribute resources
            for _, row in data.iterrows():
                epic_id = row['EpicID']
                dp_points = row['Points']
                oil_points = row['OilPoints']
                energy_points = row['EnergyPoints']

                # Ensure there is enough balance to distribute each resource
                if dp_points > dp_balance or oil_points > oil_balance or energy_points > energy_balance:
                    results.append(f"Not enough resources to distribute to {epic_id}. Remaining balances - DP: {dp_balance}, Oil: {oil_balance}, Energy: {energy_balance}.")
                    continue

                # Find the user associated with the EPIC ID
                user_id = {v: k for k, v in normalized_user_epic_ids.items()}.get(epic_id)

                if user_id:
                    # Retrieve id_wallet using EPIC-ID
                    wallet_api_url = f"https://api.staging.deverse.world/api/authenticate/{epic_id}"
                    wallet_headers = {
                        "x-dw-api-key": f"{DW_TOKEN}"  # Replace with your actual Deverse World API key
                    }

                    try:
                        wallet_response = requests.get(wallet_api_url, headers=wallet_headers)
                        if wallet_response.status_code in [200, 201]:  # Handle both 200 and 201 status codes
                            # Extract the 'id_wallet' from the 'data' key in the response
                            wallet_data = wallet_response.json().get('data', {})
                            id_wallet = wallet_data.get('thx', {}).get('id_wallet')

                            if not id_wallet:
                                results.append(f"Failed to retrieve wallet for Epic ID {epic_id}. 'id_wallet' not found.")
                                continue
                        else:
                            results.append(f"Failed to retrieve wallet for Epic ID {epic_id}. API responded with status code: {wallet_response.status_code}. Response: {wallet_response.text}")
                            continue
                    except Exception as e:
                        results.append(f"Failed to retrieve wallet for Epic ID {epic_id}. Error: {str(e)}")
                        continue

                    # Step 3: Transfer resources
                    def transfer_resource(resource_name, points, asset_id):
                        if points > 0:
                            transfer_api_url = "https://api.helpers.testnet.thxnet.org/rest/v0.5/me/testnet_leafchain_aether/ft/transfer"
                            transfer_payload = {
                                "receiver_id_wallet_address": id_wallet,
                                "transfer_value_human": points,
                                "native": False,
                                "asset_id": asset_id
                            }
                            transfer_headers = {
                                "Authorization": f"Bearer {BEAR_TOKEN}"  # Replace with your actual bearer token
                            }

                            try:
                                transfer_response = requests.post(transfer_api_url, headers=transfer_headers, json=transfer_payload)
                                if transfer_response.status_code == 200:
                                    results.append(f"Successfully distributed {points} {resource_name} to {epic_id} (User: {user_id}).")
                                    return points  # Return the points to decrement the balance
                                else:
                                    results.append(f"Failed to distribute {points} {resource_name} to {epic_id} (User: {user_id}). API responded with status code: {transfer_response.status_code}.")
                                    return 0
                            except Exception as e:
                                results.append(f"Failed to distribute {points} {resource_name} to {epic_id} (User: {user_id}). Error: {str(e)}")
                                return 0
                        return 0

                    # Transfer DP, Oil, and Energy
                    dp_balance -= transfer_resource("DP", dp_points, 1)
                    oil_balance -= transfer_resource("Oil", oil_points, 2)
                    energy_balance -= transfer_resource("Energy", energy_points, 3)

                else:
                    results.append(f"User with Epic ID {epic_id} not found in the server.")

            # Report the results of the distribution process
            result_message = "\n".join(results)
            await interaction.followup.send(f"Distribution process completed:\n{result_message}", ephemeral=True)
        else:
            await interaction.followup.send("No EPIC Account IDs have been set yet.", ephemeral=True)


# Register the command group with the bot
bot.tree.add_command(DwCommands())

# Run the bot with your token
bot.run(DISCORD_TOKEN)