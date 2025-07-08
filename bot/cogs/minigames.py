import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from . import EMBED_COLOR


class MinigamesCog(commands.GroupCog, name="minigames"):
    """Commands for playing fun minigames like Tic-Tac-Toe."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.games = (
            {}
        )  # Dictionary to store active games (key: channel_id, value: game instance)

    @app_commands.command(
        name="tic-tac-toe",
        description="Start a game of Tic-Tac-Toe with another player.",
    )
    @app_commands.describe(
        opponent="The user you want to challenge to a game of Tic-Tac-Toe."
    )
    async def tic_tac_toe(
        self, interaction: discord.Interaction, opponent: discord.Member
    ):
        """Start a game of Tic-Tac-Toe with another player."""
        if opponent == interaction.user:
            await interaction.response.send_message(
                "You cannot play against yourself!", ephemeral=True
            )
            return

        if opponent.bot:
            await interaction.response.send_message(
                "You cannot play against a bot!", ephemeral=True
            )
            return

        # Initialize the game board
        game_board = [["⬜" for _ in range(3)] for _ in range(3)]
        current_player = interaction.user
        self.games[interaction.channel.id] = {
            "board": game_board,
            "players": [interaction.user, opponent],
            "turn": current_player,
            "symbols": {interaction.user: "❌", opponent: "⭕"},
            "view": None,  # Store the View object for button management
        }

        # Create the initial game view with buttons
        view = self.create_game_view(interaction.channel.id)
        self.games[interaction.channel.id]["view"] = view

        # Send the initial game message
        embed = self.create_game_embed(interaction.channel.id)
        await interaction.response.send_message(
            f"{current_player.mention} is {self.games[interaction.channel.id]['symbols'][current_player]}, {opponent.mention} is {self.games[interaction.channel_id]['symbols'][opponent]}",
            embed=embed,
            view=view,
        )

    def create_game_embed(self, channel_id):
        """Create an embed displaying the current state of the Tic-Tac-Toe board."""
        game = self.games[channel_id]
        board = game["board"]

        board_str = "\n".join([" ".join(row) for row in board])
        embed = discord.Embed(
            title="Tic-Tac-Toe",
            description=f"{board_str}\n\n{game['turn'].mention}'s turn ({game['symbols'][game['turn']]})",
            color=EMBED_COLOR,
        )
        return embed

    def create_game_view(self, channel_id):
        """Create a View with buttons for the Tic-Tac-Toe board."""
        game = self.games[channel_id]
        view = View(timeout=None)  # Persistent view

        for row in range(3):
            for col in range(3):
                button = TicTacToeButton(row, col, game["board"][row][col])
                button.callback = self.on_button_click
                view.add_item(button)

        return view

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks for the Tic-Tac-Toe game."""
        channel_id = interaction.channel.id
        if channel_id not in self.games:
            await interaction.response.send_message(
                "This game has ended.", ephemeral=True
            )
            return

        game = self.games[channel_id]
        if interaction.user != game["turn"]:
            await interaction.response.send_message(
                "It's not your turn!", ephemeral=True
            )
            return

        button: TicTacToeButton = interaction.data["custom_id"]
        row, col = map(int, button.split(":"))  # Extract row and column from custom_id

        # Check if the selected cell is empty
        if game["board"][row][col] != "⬜":
            await interaction.response.send_message(
                "That cell is already taken!", ephemeral=True
            )
            return

        # Update the board
        game["board"][row][col] = game["symbols"][game["turn"]]

        # Check for a winner or a draw
        winner = self.check_winner(game["board"], game["symbols"])
        if winner:
            embed = self.create_game_embed(channel_id)
            await interaction.response.edit_message(embed=embed, view=None)
            await interaction.followup.send(
                f"🎉 {winner.mention} wins! 🎉", ephemeral=True
            )
            del self.games[channel_id]
            return

        if all(cell != "⬜" for row in game["board"] for cell in row):
            embed = self.create_game_embed(channel_id)
            await interaction.response.edit_message(embed=embed, view=None)
            await interaction.followup.send("It's a draw!", ephemeral=True)
            del self.games[channel_id]
            return

        # Switch turns
        game["turn"] = next(
            player for player in game["players"] if player != game["turn"]
        )

        # Update the view
        embed = self.create_game_embed(channel_id)
        view = self.create_game_view(channel_id)
        game["view"] = view
        await interaction.response.edit_message(embed=embed, view=view)

    def check_winner(self, board, symbols):
        """Check if there is a winner on the board."""
        # Check rows, columns, and diagonals
        for i in range(3):
            if board[i][0] == board[i][1] == board[i][2] != "⬜":  # Rows
                return next(
                    player
                    for player, symbol in symbols.items()
                    if symbol == board[i][0]
                )
            if board[0][i] == board[1][i] == board[2][i] != "⬜":  # Columns
                return next(
                    player
                    for player, symbol in symbols.items()
                    if symbol == board[0][i]
                )

        if (
            board[0][0] == board[1][1] == board[2][2] != "⬜"
        ):  # Diagonal top-left to bottom-right
            return next(
                player for player, symbol in symbols.items() if symbol == board[0][0]
            )
        if (
            board[0][2] == board[1][1] == board[2][0] != "⬜"
        ):  # Diagonal top-right to bottom-left
            return next(
                player for player, symbol in symbols.items() if symbol == board[0][2]
            )

        return None


class TicTacToeButton(Button):
    """A button representing a cell in the Tic-Tac-Toe board."""

    def __init__(self, row: int, col: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.custom_id = f"{row}:{col}"  # Unique identifier for the button


async def setup(bot):
    await bot.add_cog(MinigamesCog(bot))
