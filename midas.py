import cloudscraper
import time
import configparser
import logging
import os
from typing import Tuple, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Color codes for console output
CYAN = '\033[96m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

AUTH_FILE = config.get('settings', 'auth_file', fallback='auth.txt')
SLEEP_BETWEEN_ACCOUNTS = config.getint('settings', 'sleep_between_accounts', fallback=10)
SLEEP_BETWEEN_RUNS = config.getint('settings', 'sleep_between_runs', fallback=8 * 3600)
MAX_RETRIES = config.getint('settings', 'max_retries', fallback=3)


def post_request(url: str, headers: Dict[str, str], payload: Any = None, retries: int = 0) -> Tuple[Any, Any]:
    """Makes a POST request using cloudscraper."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.post(url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            return response.json(), response.cookies
        except ValueError:
            return response.text, response.cookies
    except Exception as e:
        if retries < MAX_RETRIES:
            logger.warning(f"Request failed: {e}. Retrying in 5 seconds... (Attempt {retries + 1}/{MAX_RETRIES})")
            time.sleep(5)
            return post_request(url, headers, payload, retries + 1)
        else:
            logger.error(f"Request failed after multiple retries: {e}")
            return None, None


def get_request(url: str, headers: Dict[str, str], retries: int = 0) -> Any:
    """Makes a GET request using cloudscraper."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, headers=headers)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            logger.warning("Response is not JSON.")
            return None
    except Exception as e:
        if retries < MAX_RETRIES:
            logger.warning(f"Request failed: {e}. Retrying in 5 seconds... (Attempt {retries + 1}/{MAX_RETRIES})")
            time.sleep(5)
            return get_request(url, headers, retries + 1)
        else:
            logger.error(f"Request failed after multiple retries: {e}")
            return None


def read_init_data(filename: str) -> list[str]:
    """Reads init data from a file."""
    try:
        with open(filename, 'r') as file:
            init_data_list = [line.strip() for line in file if line.strip()]
            return init_data_list
    except FileNotFoundError:
        logger.error(f"File {filename} not found.")
        return []


def get_streak_info(headers: Dict[str, str]):
    """Gets and prints streak information."""
    url_streak = "https://api-tg-app.midas.app/api/streak"
    streak_data = get_request(url_streak, headers)

    if streak_data:
        streak_days_count = streak_data.get("streakDaysCount", "Not found")
        next_rewards = streak_data.get("nextRewards", {})
        points = next_rewards.get("points", "Not found")
        tickets = next_rewards.get("tickets", "Not found")
        claimable = streak_data.get("claimable", False)

        logger.info(f"Streak Days Count: {streak_days_count}")
        logger.info(f"Claimable Rewards - Points: {GREEN}{points}{RESET}, Tickets: {GREEN}{tickets}{RESET}")

        if claimable:
            logger.info(f"{GREEN}Streak available to claim.{RESET}")
            claim_streak(headers)
        else:
            logger.warning(f"{YELLOW}Streak not available to claim.{RESET}")
    else:
        logger.error("Error: Could not access streak API.")


def claim_streak(headers: Dict[str, str]):
    """Claims the daily streak reward."""
    url_claim = "https://api-tg-app.midas.app/api/streak"
    response, _ = post_request(url_claim, headers)

    if response:
        points = response.get("points", "Not found")
        tickets = response.get("tickets", "Not found")
        logger.info(f"{GREEN}Daily ticket and point claim successful!{RESET}")
    else:
        logger.error(f"{RED}Error: Failed to claim daily reward.{RESET}")



def get_user_info(headers: Dict[str, str]) -> Tuple[int, int]:
    """Gets and prints user information."""
    url_user = "https://api-tg-app.midas.app/api/user"
    user_data = get_request(url_user, headers)

    if user_data:
        telegram_id = user_data.get("telegramId", "Not found")
        username = user_data.get("username", "Not found")
        first_name = user_data.get("firstName", "Not found")
        points = user_data.get("points", "Not found")
        tickets = user_data.get("tickets", 0)
        games_played = user_data.get("gamesPlayed", "Not found")
        streak_days_count = user_data.get("streakDaysCount", "Not found")

        logger.info(f"Telegram ID: {telegram_id}")
        logger.info(f"Username: {CYAN}{username}{RESET}")
        logger.info(f"First Name: {CYAN}{first_name}{RESET}")
        logger.info(f"Points: {GREEN}{points}{RESET}")
        logger.info(f"Tickets: {GREEN if tickets > 0 else RED}{tickets}{RESET}")
        logger.info(f"Games Played: {games_played}")
        logger.info(f"Streak Days Count: {streak_days_count}")

        return tickets, points
    else:
        logger.error("Error: Could not access user API.")
        return 0, 0


def check_referral_status(headers: Dict[str, str]) -> Tuple[int, int]:
    """Checks and claims referral rewards if available."""
    url_referral = "https://api-tg-app.midas.app/api/referral/status"
    url_referral_claim = "https://api-tg-app.midas.app/api/referral/claim"

    referral_data = get_request(url_referral, headers)

    if referral_data:
        can_claim = referral_data.get("canClaim", False)
        if can_claim:
            logger.info(f"{GREEN}Referral claim available! Executing claim...{RESET}")
            claim_response, _ = post_request(url_referral_claim, headers)

            if claim_response:
                total_points = claim_response.get("totalPoints", 0)
                total_tickets = claim_response.get("totalTickets", 0)
                logger.info(f"{GREEN}Referral claim successful!{RESET} You received {GREEN}{total_points}{RESET} points and {GREEN}{total_tickets}{RESET} tickets.")
                return total_points, total_tickets
            else:
                logger.error(f"{RED}Error executing referral claim.{RESET}")
                return 0, 0
        else:
            logger.warning(f"{YELLOW}No referral claims available at this time.{RESET}")
            return 0, 0
    else:
        logger.error(f"{RED}Request error.{RESET}")
        return 0, 0




def play_game(headers: Dict[str, str], tickets: int) -> int:
    """Plays the game using available tickets."""
    url_game = "https://api-tg-app.midas.app/api/game/play"
    total_points = 0

    while tickets > 0:
        for i in range(3, 0, -1):
            print(f"Starting game in {YELLOW}{i}{RESET} seconds...", end='\r')
            time.sleep(1)

        logger.info(f"{YELLOW}Starting game...{RESET}")
        game_data, _ = post_request(url_game, headers)

        if game_data:
            points_earned = game_data.get("points", 0)
            total_points += points_earned
            tickets -= 1
            logger.info(f"Earned {GREEN}{points_earned}{RESET} points, Total Points: {GREEN}{total_points}{RESET}, Remaining Tickets: {YELLOW}{tickets}{RESET}")
        else:
            logger.error(f"{RED}Error playing game.{RESET}")
            break  # Exit the loop if there's an error

    return total_points



def process_init_data(init_data: str):
    """Processes the initData and performs game actions."""
    logger.info(f"Processing initData: {YELLOW}...{init_data[-20:]}{RESET}")

    url_register = "https://api-tg-app.midas.app/api/auth/register"
    headers_register = {
        "Accept": "application/json, text/plain, */*",
       # ...(rest of the headers)
    }

    payload = {
        "initData": init_data
    }

    response_text, cookies = post_request(url_register, headers_register, payload)

    if response_text:
        logger.info(f"Token received: {YELLOW}...{response_text[-20:]}{RESET}")
        cookies_dict = cookies.get_dict()
        cookies_preview = {key: f"...{value[-20:]}" for key, value in cookies_dict.items()}
        logger.info(f"Cookies received: {YELLOW}{cookies_preview}{RESET}")

        token = response_text

        headers_user = {
            "Accept": "application/json, text/plain, */*",
            # ... (rest of the user headers)
            "Authorization": f"Bearer {token}",
            "Cookie": "; ".join([f"{key}={value}" for key, value in cookies.get_dict().items()])
        }

        get_streak_info(headers_user)
        check_referral_status(headers_user)
        tickets, points = get_user_info(headers_user)

        if tickets > 0:
            total_points = play_game(headers_user, tickets)
            logger.info(f"Total Points after playing games: {GREEN}{total_points}{RESET}")
        else:
            logger.warning("No tickets available to play games.")
    else:
        logger.error("Error: Could not get token.")


def main():
    """Main function."""
    init_data_list = read_init_data(AUTH_FILE)

    if not init_data_list:
        logger.error("No init data found. Exiting.")
        return

    while True:
        for init_data in init_data_list:
            process_init_data(init_data)
            logger.info(f"Sleeping for {SLEEP_BETWEEN_ACCOUNTS} seconds before processing the next account...")
            time.sleep(SLEEP_BETWEEN_ACCOUNTS)

        logger.info(f"Finished processing all init data. Restarting in {SLEEP_BETWEEN_RUNS / 3600} hours...")
        time.sleep(SLEEP_BETWEEN_RUNS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Program interrupted by user. Exiting.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")