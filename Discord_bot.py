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
load_dotenv()  # Loads the environment variables from a .env file

# Retrieve the Discord token and other tokens from the environment
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')  # Gets the Discord bot token from the environment
BEAR_TOKEN = os.getenv('BEAR_TOKEN')  # Gets the bearer token for API authentication
DW_TOKEN = os.getenv('DW_TOKEN')  # Gets the Deverse World API key from the environment

if DISCORD_TOKEN is None:
    raise ValueError("Discord token not found. Please check your .env file.")  # Raises an error if the token is not found

# Set up intents
intents = discord.Intents.default()  # Creates a default set of intents for the bot
intents.messages = True  # Allows the bot to receive messages
intents.message_content = True  # Allows the bot to read the content of the messages
intents.guilds = True  # Allows the bot to access guild information

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)  # Initializes the bot with a command prefix and intents

# Function to validate EPIC Account ID
def is_valid_epic_id(epic_id):
    return len(epic_id) == 32 and epic_id.isalnum()  # Checks if the EPIC ID is 32 characters long and alphanumeric

# JSON file path for storing user EPIC IDs
epic_ids_file = 'epic_ids.json'  # Specifies the path to the JSON file where EPIC IDs are stored

# Load the user_epic_ids from a JSON file
def load_epic_ids():
    try:
        with open(epic_ids_file, 'r') as f:
            return json.load(f)  # Loads existing EPIC IDs from the JSON file
    except FileNotFoundError:
        return {}  # Returns an empty dictionary if the file doesn't exist

# Save the user_epic_ids to a JSON file
def save_epic_ids():
    with open(epic_ids_file, 'w') as f:
        json.dump(user_epic_ids, f)  # Saves the current EPIC IDs to the JSON file

# Load existing data when the bot starts
user_epic_ids = load_epic_ids()  # Loads the EPIC IDs from the JSON file at startup

# Admin role name
admin_role_name = "Admins"  # Sets the name of the admin role that has special permissions

# Function to check if the user has the Admin role
def is_admin(interaction: discord.Interaction):
    admin_role = discord.utils.get(interaction.guild.roles, name=admin_role_name)
    return admin_role in interaction.user.roles  # Checks if the user invoking the command has the Admin role

# Cooldown dictionary
cooldowns = defaultdict(lambda: 0)  # Initializes a cooldown dictionary to prevent spamming

# Common messages used throughout the bot
DM_REASON = "To protect your privacy and prevent potential attacks on your account, please check your DMs to provide your EPIC Account ID."
PROVIDE_EPIC_ID_MSG = "Please provide your EPIC Account ID within 60 seconds:"
INVALID_EPIC_ID_MSG = "The provided EPIC Account ID is invalid. Please ensure it is a 32 character alphanumeric string."
ID_IN_USE_MSG = "The provided EPIC Account ID is already in use. Please provide a different ID."
THANK_YOU_MSG = "Thank you! Your EPIC Account ID has been saved."
TOOK_TOO_LONG_MSG = "You took too long to respond. Please try again."
EPIC_ID_SET_MSG = "Click the button below to set your EPIC Account ID."
EPIC_ID_EDIT_MSG = "Click the button below to edit your EPIC Account ID."
COOLDOWN_TIME = 10  # Cooldown time in seconds to prevent spamming

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
                return id_wallet, None  # Successfully retrieved the wallet ID
            else:
                return None, "'id_wallet' not found in the response data."  # Handle the case where 'id_wallet' is missing
        else:
            return None, f"API responded with status code: {wallet_response.status_code}. Response: {wallet_response.text}"
    except Exception as e:
        return None, str(e)  # Return None for id_wallet and an error message if something goes wrong

# Function to retrieve the balance of a wallet using its id_wallet
def get_wallet_balance(id_wallet):
    balance_api_url = f"https://api.helpers.testnet.thxnet.org/rest/v0.5/id_wallet/{id_wallet}/testnet_leafchain_aether/fts"
    balance_headers = {"Authorization": f"Bearer {BEAR_TOKEN}"}
    
    try:
        balance_response = requests.get(balance_api_url, headers=balance_headers)
        if balance_response.status_code == 200:
            balance_data = balance_response.json().get('result', {})
            return balance_data, None  # Return the balance data if the API call is successful
        else:
            return None, f"API responded with status code: {balance_response.status_code}."
    except Exception as e:
        return None, str(e)  # Return None for balance data and an error message if something goes wrong

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
            return True, None  # Return True if the transfer was successful
        else:
            return False, f"API responded with status code: {transfer_response.status_code}."
    except Exception as e:
        return False, str(e)  # Return False and an error message if something goes wrong

# Event triggered when the bot is ready
@bot.event
async def on_ready():
    await bot.tree.sync(guild=None)  # Sync commands globally
    print(f'We have logged in as {bot.user} and synced the commands.')  # Print a message indicating the bot is ready

# Create a command group
class DwCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="dw-commands", description="Commands for managing EPIC IDs and game info")  # Initializes the command group

    # Help command within the dw-commands group
    @app_commands.command(name="help", description="Displays information on how to use the dw-commands and their descriptions.")
    async def dw_help(self, interaction: discord.Interaction):
        # Create an embed for the help message
        embed = discord.Embed(title="Help - DW Commands", color=discord.Color.blue())
        
        # Check if the bot has an avatar and set it as the thumbnail if it does
        if bot.user.avatar:
            embed.set_thumbnail(url=bot.user.avatar.url)
        
        # Add a field for each command and its description
        embed.add_field(name="/dw-commands set", value="Set your EPIC Account ID. Follow the instructions provided after using the command.", inline=False)
        embed.add_field(name="/dw-commands view", value="View your EPIC Account ID and wallet balances (DP, Oil, Energy).", inline=False)
        embed.add_field(name="/dw-commands edit", value="Edit your existing EPIC Account ID.", inline=False)
        embed.add_field(name="/dw-commands list (Admin only)", value="List all EPIC Account IDs registered with the bot. Admins can also export this list.", inline=False)
        embed.add_field(name="/dw-commands distribute (Admin only)", value="Distribute DP, Oil, and Energy to users.", inline=False)
        
        embed.add_field(name="Example Commands", value="• Use `/dw-commands set` to set your EPIC Account ID.\n• Use `/dw-commands view` to view your account info.", inline=False)
        
        embed.set_footer(text="For more help, contact an Admin or open a ticket in #ticketing channel.")
        
        # Send the help embed to the user
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Command to set the EPIC Account ID
    @app_commands.command(name="set", description="Set your EPIC Account ID")
    async def dw_set(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)  # Get the user's Discord ID as a string

        # Callback function for the button to set EPIC Account ID
        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return  # Prevent the user from spamming the button

            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME  # Update the cooldown time

            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return  # Ensure the button interaction is authorized

            if user_id in user_epic_ids:
                await button_interaction.response.send_message("You already have an EPIC Account ID set. You cannot set it again.", ephemeral=True)
                return  # Prevent users from setting their EPIC ID again if it's already set

            await button_interaction.response.send_message(DM_REASON, ephemeral=True)  # Prompt the user to check their DMs for privacy

            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)  # Check if the message is from the user in DMs

            try:
                await button_interaction.user.send(PROVIDE_EPIC_ID_MSG)  # Ask the user to provide their EPIC ID in DMs
                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)  # Wait for the user's response
                    epic_id = msg.content

                    if is_valid_epic_id(epic_id):  # Validate the provided EPIC ID
                        if epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)  # Check if the EPIC ID is already in use
                        else:
                            user_epic_ids[user_id] = epic_id  # Save the EPIC ID for the user
                            save_epic_ids()  # Save the updated EPIC IDs to the JSON file
                            await button_interaction.user.send(THANK_YOU_MSG)  # Thank the user for providing their EPIC ID
                            await button_interaction.followup.send('Setup completed successfully!', ephemeral=True)
                            await interaction.channel.send(f'{button_interaction.user.mention} has successfully set their EPIC Account ID.')
                            await interaction.delete_original_response()  # Delete the original interaction response
                            break
                    else:
                        await button_interaction.user.send(INVALID_EPIC_ID_MSG)  # Notify the user if the EPIC ID is invalid
            except asyncio.TimeoutError:
                await button_interaction.user.send(TOOK_TOO_LONG_MSG)  # Notify the user if they took too long to respond
                await button_interaction.followup.send(TOOK_TOO_LONG_MSG, ephemeral=True)
                await interaction.delete_original_response()  # Delete the original interaction response if timed out

            set_button.disabled = True  # Disable the button after interaction
            view.clear_items()  # Clear all items from the view to prevent further interactions
            try:
                await button_interaction.message.edit(view=view)  # Update the message view
            except discord.errors.NotFound:
                pass  # Handle the case where the message is already deleted

        set_button = Button(label="Set EPIC Account ID", style=discord.ButtonStyle.primary)  # Create a button to set the EPIC ID
        set_button.callback = button_callback  # Set the callback function for the button

        help_button = Button(label="Help", style=discord.ButtonStyle.link, url="https://www.epicgames.com/help/en-US/c-Category_EpicAccount/c-AccountSecurity/what-is-an-epic-account-id-and-where-can-i-find-it-a000084674")  # Create a help button linking to Epic Games' support page

        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()  # Delete the original interaction response
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)  # Notify the user if the message was already deleted

        close_button = Button(label="Close", style=discord.ButtonStyle.danger)  # Create a close button
        close_button.callback = close_button_callback  # Set the callback function for the close button

        view = View()  # Create a view to hold the buttons
        view.add_item(set_button)  # Add the set button to the view
        view.add_item(help_button)  # Add the help button to the view
        view.add_item(close_button)  # Add the close button to the view

        await interaction.response.send_message(EPIC_ID_SET_MSG, view=view, ephemeral=True)  # Send the message with the buttons

    # Command to view the EPIC Account ID
    @app_commands.command(name="view", description="View your EPIC Account ID and balance")
    async def dw_view(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)  # Get the user's Discord ID as a string

        epic_id = user_epic_ids.get(user_id)  # Retrieve the EPIC ID associated with the user's Discord ID
        if not epic_id:
            await interaction.response.send_message('You have not provided an EPIC Account ID yet.', ephemeral=True)
            return  # Notify the user if they haven't set an EPIC ID

        await interaction.response.defer(ephemeral=True)  # Defer the response to ensure enough time for processing

        id_wallet, error = get_wallet_by_epic_id(epic_id)  # Retrieve the wallet ID using the EPIC ID
        if not id_wallet:
            # If wallet retrieval fails, explicitly set balances to None
            dp_balance = None
            oil_balance = None
            energy_balance = None

            # Notify the user of the failure and include their Discord name and EPIC Account ID
            await interaction.followup.send(
                f"Failed to retrieve wallet for {interaction.user.name} (EPIC Account ID: {epic_id}). {error}", 
                ephemeral=True
            )
        else:
            # Retrieve the wallet balances if wallet retrieval was successful
            balance_data, error = get_wallet_balance(id_wallet)
            if error:
                dp_balance = None
                oil_balance = None
                energy_balance = None

                await interaction.followup.send(f"Failed to retrieve balance. {error}", ephemeral=True)
            else:
                dp_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 1), 0)
                oil_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 2), 0)
                energy_balance = next((item['balance'] for item in balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 3), 0)

        embed = discord.Embed(title="Your Account Information", color=discord.Color.blue())  # Create an embed for displaying account information
        embed.add_field(name="Discord Name", value=interaction.user.name, inline=True)  # Add the user's Discord name to the embed
        embed.add_field(name="EPIC Account ID", value=epic_id, inline=True)  # Add the EPIC ID to the embed
        embed.add_field(name="Wallet ID", value=f"{id_wallet}" if id_wallet else "None", inline=False)  # Add the wallet ID or "None" to the embed
        embed.add_field(name="DP", value=f"{dp_balance}" if dp_balance is not None else "None", inline=True)  # Add the DP balance or "None" to the embed
        embed.add_field(name="Oil", value=f"{oil_balance}" if oil_balance is not None else "None", inline=True)  # Add the oil balance or "None" to the embed
        embed.add_field(name="Energy", value=f"{energy_balance}" if energy_balance is not None else "None", inline=True)  # Add the energy balance or "None" to the embed
        embed.set_thumbnail(url=interaction.user.avatar.url)  # Set the user's avatar as the thumbnail in the embed

        await interaction.followup.send(embed=embed, ephemeral=True)  # Send the embed as a response

    # Command to edit the EPIC Account ID
    @app_commands.command(name="edit", description="Edit your EPIC Account ID")
    async def dw_edit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)  # Get the user's Discord ID as a string

        async def button_callback(button_interaction):
            now = time.time()
            if now < cooldowns[button_interaction.user.id]:
                await button_interaction.response.send_message("You are clicking too fast! Please wait a few seconds.", ephemeral=True)
                return  # Prevent the user from spamming the button

            cooldowns[button_interaction.user.id] = now + COOLDOWN_TIME  # Update the cooldown time

            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return  # Ensure the button interaction is authorized

            if user_id not in user_epic_ids:
                await button_interaction.response.send_message("You do not have an EPIC Account ID set yet. Please set it first using the /dw set command.", ephemeral=True)
                return  # Prevent the user from editing their EPIC ID if it's not set

            await button_interaction.response.send_message(DM_REASON, ephemeral=True)  # Prompt the user to check their DMs for privacy

            def check(msg):
                return msg.author == button_interaction.user and isinstance(msg.channel, discord.DMChannel)  # Check if the message is from the user in DMs

            try:
                await button_interaction.user.send("Please provide your new EPIC Account ID within 60 seconds:")  # Ask the user to provide their new EPIC ID in DMs
                while True:
                    msg = await bot.wait_for('message', check=check, timeout=60)  # Wait for the user's response
                    new_epic_id = msg.content

                    if is_valid_epic_id(new_epic_id):  # Validate the provided EPIC ID
                        if new_epic_id in user_epic_ids.values():
                            await button_interaction.user.send(ID_IN_USE_MSG)  # Check if the new EPIC ID is already in use
                        else:
                            user_epic_ids[user_id] = new_epic_id  # Save the new EPIC ID for the user
                            save_epic_ids()  # Save the updated EPIC IDs to the JSON file
                            await button_interaction.user.send('Thank you! Your EPIC Account ID has been updated.')  # Thank the user for providing their new EPIC ID
                            await button_interaction.followup.send('Update completed successfully!', ephemeral=True)
                            await interaction.channel.send(f'{button_interaction.user.mention} has successfully updated their EPIC Account ID.')
                            await interaction.delete_original_response()  # Delete the original interaction response
                            break
                    else:
                        await button_interaction.user.send(INVALID_EPIC_ID_MSG)  # Notify the user if the EPIC ID is invalid
            except asyncio.TimeoutError:
                await button_interaction.user.send(TOOK_TOO_LONG_MSG)  # Notify the user if they took too long to respond
                await button_interaction.followup.send(TOOK_TOO_LONG_MSG, ephemeral=True)
                await interaction.delete_original_response()  # Delete the original interaction response if timed out

            button.disabled = True  # Disable the button after interaction
            view.clear_items()  # Clear all items from the view to prevent further interactions
            try:
                await button_interaction.message.edit(view=view)  # Update the message view
            except discord.errors.NotFound:
                pass  # Handle the case where the message is already deleted

        button = Button(label="Edit EPIC Account ID", style=discord.ButtonStyle.primary)  # Create a button to edit the EPIC ID
        button.callback = button_callback  # Set the callback function for the button

        # Close button callback
        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()  # Delete the original interaction response
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)  # Notify the user if the message was already deleted

        close_button = Button(label="Close", style=discord.ButtonStyle.danger)  # Create a close button
        close_button.callback = close_button_callback  # Set the callback function for the close button

        view = View()  # Create a view to hold the buttons
        view.add_item(button)  # Add the edit button to the view
        view.add_item(close_button)  # Add the close button to the view

        await interaction.response.send_message(EPIC_ID_EDIT_MSG, view=view, ephemeral=True)  # Send the message with the buttons

    # Command to remove the EPIC Account ID
    @app_commands.command(name="remove", description="Remove your EPIC Account ID")
    async def dw_remove(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)  # Get the user's Discord ID as a string

        # Check if the user has an EPIC Account ID
        if user_id not in user_epic_ids:
            await interaction.response.send_message("You don't have an EPIC Account ID set.", ephemeral=True)
            return  # If the user doesn't have an EPIC ID, notify them and exit

        # Confirmation button interaction
        async def confirm_button_callback(button_interaction):
            if button_interaction.user.id != int(user_id):
                await button_interaction.response.send_message("You are not authorized to use this button.", ephemeral=True)
                return  # Ensure the button interaction is authorized

            del user_epic_ids[user_id]  # Remove the EPIC ID from the dictionary
            save_epic_ids()  # Save the updated EPIC IDs to the JSON file

            await button_interaction.response.send_message("Your EPIC Account ID has been removed.", ephemeral=True)
            await interaction.channel.send(f"{button_interaction.user.mention} has successfully removed their EPIC Account ID.")
            await interaction.delete_original_response()  # Delete the original interaction response

        confirm_button = Button(label="Confirm", style=discord.ButtonStyle.danger)  # Create a confirm button
        confirm_button.callback = confirm_button_callback  # Set the callback for the button

        close_button = Button(label="Cancel", style=discord.ButtonStyle.secondary)  # Create a close button

        async def close_button_callback(button_interaction):
            try:
                await interaction.delete_original_response()  # Delete the original interaction response
            except discord.errors.NotFound:
                await button_interaction.response.send_message("Message already deleted.", ephemeral=True)  # Notify the user if the message was already deleted

        close_button.callback = close_button_callback  # Set the callback for the close button

        view = View()  # Create a view to hold the buttons
        view.add_item(confirm_button)  # Add the confirm button
        view.add_item(close_button)  # Add the close button

        await interaction.response.send_message("Are you sure you want to remove your EPIC Account ID?", view=view, ephemeral=True)

    # Command to list all EPIC Account IDs (Admin only)
    @app_commands.command(name="list", description="List all EPIC Account IDs (Admin only)")
    async def dw_list(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You do not have the necessary permissions to use this command.", ephemeral=True)
            return  # Ensure that only users with the Admin role can use this command

        if user_epic_ids:
            embed = discord.Embed(title="List of EPIC Account IDs", color=discord.Color.green())  # Create an embed for listing EPIC IDs
            data_list = []

            for user_id, epic_id in user_epic_ids.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else f"User ID: {user_id}"  # Get the username or user ID if the user is not found
                embed.add_field(name=username, value=epic_id, inline=False)  # Add each user's EPIC ID to the embed
                data_list.append({'EpicID': epic_id, 'Points': 0, 'OilPoints': 0, 'EnergyPoints': 0})  # Prepare data for CSV export

            export_button = Button(label="Export to CSV", style=discord.ButtonStyle.primary)  # Create an export button to export the list to a CSV file

            async def export_button_callback(button_interaction):
                df = pd.DataFrame(data_list)
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                        temp_file_path = tmp_file.name
                        df.to_csv(temp_file_path, index=False)  # Save the data to a temporary CSV file

                    await button_interaction.response.send_message(file=discord.File(temp_file_path, filename="epic_ids_list.csv"), ephemeral=True)  # Send the CSV file as a response
                finally:
                    os.remove(temp_file_path)  # Clean up the temporary file after sending

            export_button.callback = export_button_callback  # Set the callback function for the export button

            close_button = Button(label="Close", style=discord.ButtonStyle.danger)  # Create a close button

            async def close_button_callback(button_interaction):
                try:
                    await interaction.delete_original_response()  # Delete the original interaction response
                except discord.errors.NotFound:
                    await button_interaction.response.send_message("Message already deleted.", ephemeral=True)  # Notify the user if the message was already deleted

            close_button.callback = close_button_callback  # Set the callback function for the close button

            view = View()  # Create a view to hold the buttons
            view.add_item(export_button)  # Add the export button to the view
            view.add_item(close_button)  # Add the close button to the view

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)  # Send the embed with the buttons
        else:
            await interaction.response.send_message("No EPIC Account IDs have been set yet.", ephemeral=True)  # Notify the user if there are no EPIC IDs set

    # Command to distribute DP based on a CSV file (Admin only)
    @app_commands.command(name="distribute", description="Distribute DP, Oil, and Energy based on a CSV file (Admin only)")
    async def dw_distribute(self, interaction: Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)  # Defer the response to ensure enough time for processing

        if not is_admin(interaction):
            await interaction.followup.send("You do not have the necessary permissions to use this command.", ephemeral=True)
            return  # Ensure that only users with the Admin role can use this command

        if user_epic_ids:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                temp_file_path = tmp_file.name

            await file.save(fp=temp_file_path)  # Save the uploaded CSV file to a temporary location

            data = pd.read_csv(temp_file_path)  # Load the CSV file into a DataFrame
            data.columns = data.columns.str.strip()  # Strip any whitespace from the column names

            required_columns = {"EpicID", "Points", "OilPoints", "EnergyPoints"}  # Define the required columns in the CSV
            if not required_columns.issubset(data.columns):
                await interaction.followup.send("The CSV file must contain 'EpicID', 'Points', 'OilPoints', and 'EnergyPoints' columns.", ephemeral=True)
                return  # Check if the CSV file has the required columns

            data['EpicID'] = data['EpicID'].str.strip().str.lower()  # Normalize the EPIC IDs for case-insensitive comparison
            normalized_user_epic_ids = {k: v.strip().lower() for k, v in user_epic_ids.items()}  # Normalize the stored EPIC IDs

            bot_balance_data, error = get_wallet_balance("5DSFYPkB2b6auEwZxqbkAWa213EbBfDtRuaRrnivA3RvoMyg")  # Check the bot's bank account balance
            if error or not bot_balance_data:
                await interaction.followup.send(f"Failed to check Bot Bank Account balance. {error}", ephemeral=True)
                return  # Notify the user if the balance retrieval fails

            dp_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 1), 0)
            oil_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 2), 0)
            energy_balance = next((item['balance'] for item in bot_balance_data.get('non_native_ft_balances', []) if item['asset_id'] == 3), 0)

            if dp_balance <= 0 or oil_balance <= 0 or energy_balance <= 0:
                await interaction.followup.send("Insufficient balance in the Bot Bank Account for one or more resources.", ephemeral=True)
                return  # Ensure the bot has enough resources to distribute

            results = []  # Initialize a list to store results for reporting

            for _, row in data.iterrows():
                epic_id = row['EpicID']
                dp_points = row['Points']
                oil_points = row['OilPoints']
                energy_points = row['EnergyPoints']

                if dp_points > dp_balance or oil_points > oil_balance or energy_points > energy_balance:
                    results.append(f"Not enough resources to distribute to {epic_id}.")
                    continue  # Skip the distribution if there aren't enough resources

                user_id = {v: k for k, v in normalized_user_epic_ids.items()}.get(epic_id)

                if user_id:
                    id_wallet, error = get_wallet_by_epic_id(epic_id)
                    if error or not id_wallet:
                        results.append(f"Failed to retrieve wallet for Epic ID {epic_id}. {error}")
                        continue  # Skip the distribution if the wallet retrieval fails

                    for resource_name, points, asset_id in [("DP", dp_points, 1), ("Oil", oil_points, 2), ("Energy", energy_points, 3)]:
                        if points > 0:
                            success, error = transfer_resource(id_wallet, points, asset_id)
                            if success:
                                results.append(f"Successfully distributed {points} {resource_name} to {epic_id} (User: {user_id}).")
                            else:
                                results.append(f"Failed to distribute {points} {resource_name} to {epic_id}. {error}")

                else:
                    results.append(f"User with Epic ID {epic_id} not found in the server.")  # Notify if the EPIC ID is not found

            result_message = "\n".join(results)  # Combine all results into a single message
            await interaction.followup.send(f"Distribution process completed:\n{result_message}", ephemeral=True)  # Send the results as a response
        else:
            await interaction.followup.send("No EPIC Account IDs have been set yet.", ephemeral=True)  # Notify if no EPIC IDs are set


# Register the command group with the bot
bot.tree.add_command(DwCommands())  # Add the command group to the bot's command tree

# Run the bot with your token
bot.run(DISCORD_TOKEN)  # Start the bot with the Discord token
