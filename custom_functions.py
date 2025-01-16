from dataclasses import dataclass
from typing import List, Optional
from web3 import Web3
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class FunctionResponse:
    """Standard response format for custom functions"""
    success: bool
    message: str
    data: Optional[dict] = None

# Base network configuration
BASE_RPC_URL = "https://mainnet.base.org"
USDC_CONTRACT_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base USDC

# Get the bot's Base address and private key from environment variables
BOT_ADDRESS = os.getenv("BOT_BASE_ADDRESS")
BOT_PRIVATE_KEY = os.getenv("BOT_PRIVATE_KEY")
if not BOT_ADDRESS or not BOT_ADDRESS.startswith("0x"):
    raise ValueError("BOT_BASE_ADDRESS must be set in .env file to a valid Ethereum address starting with 0x")
if not BOT_PRIVATE_KEY:
    raise ValueError("BOT_PRIVATE_KEY must be set in .env file")

# Extended USDC ABI to include transfer function
USDC_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

async def get_base_usdc_balance() -> FunctionResponse:
    """Get the current USDC balance of this bot's Base account
    
    Returns:
        FunctionResponse: Contains success status and USDC balance information
    """
    try:
        # Initialize Web3 with Base
        w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        
        # Create contract instance
        contract = w3.eth.contract(
            address=w3.to_checksum_address(USDC_CONTRACT_ADDRESS),
            abi=USDC_ABI
        )
        
        # Get balance
        balance_wei = contract.functions.balanceOf(
            w3.to_checksum_address(BOT_ADDRESS)
        ).call()
        
        # Convert to USDC (6 decimals for USDC)
        balance_usdc = balance_wei / 1e6
        
        return FunctionResponse(
            success=True,
            message=f"Current USDC balance on Base: {balance_usdc:.2f} USDC",
            data={
                "balance": balance_usdc,
                "balance_wei": balance_wei,
                "address": BOT_ADDRESS
            }
        )
    except Exception as e:
        return FunctionResponse(
            success=False,
            message=f"Failed to get USDC balance: {str(e)}"
        )

async def send_usdc(to_address: str, amount: float) -> FunctionResponse:
    """Send USDC from the bot's account to a specified address
    
    Args:
        to_address (str): The recipient's Ethereum address
        amount (float): Amount of USDC to send
        
    Returns:
        FunctionResponse: Contains success status and transaction information
    """
    try:
        # Initialize Web3 with Base
        w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        
        # Validate address
        if not Web3.is_address(to_address):
            return FunctionResponse(
                success=False,
                message="Invalid Ethereum address provided"
            )
            
        # Create contract instance
        contract = w3.eth.contract(
            address=w3.to_checksum_address(USDC_CONTRACT_ADDRESS),
            abi=USDC_ABI
        )
        
        # Convert amount to wei (USDC has 6 decimals)
        amount_wei = int(amount * 1e6)
        
        # Check balance
        current_balance = contract.functions.balanceOf(
            w3.to_checksum_address(BOT_ADDRESS)
        ).call()
        
        if current_balance < amount_wei:
            return FunctionResponse(
                success=False,
                message=f"Insufficient balance. Have {current_balance/1e6:.2f} USDC, need {amount} USDC"
            )
            
        # Prepare transaction
        nonce = w3.eth.get_transaction_count(BOT_ADDRESS)
        
        transfer_txn = contract.functions.transfer(
            w3.to_checksum_address(to_address),
            amount_wei
        ).build_transaction({
            'from': BOT_ADDRESS,
            'nonce': nonce,
            'gas': 100000,  # Estimated gas limit
            'gasPrice': w3.eth.gas_price
        })
        
        # Sign transaction
        signed_txn = w3.eth.account.sign_transaction(
            transfer_txn,
            private_key=BOT_PRIVATE_KEY
        )
        
        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        # Wait for transaction receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt['status'] == 1:
            return FunctionResponse(
                success=True,
                message=f"Successfully sent {amount} USDC to {to_address}",
                data={
                    'tx_hash': tx_hash.hex(),
                    'amount': amount,
                    'recipient': to_address
                }
            )
        else:
            return FunctionResponse(
                success=False,
                message="Transaction failed",
                data={'tx_hash': tx_hash.hex()}
            )
            
    except Exception as e:
        return FunctionResponse(
            success=False,
            message=f"Failed to send USDC: {str(e)}"
        )

async def get_weather(city: str, country: Optional[str] = None) -> FunctionResponse:
    """Get the current weather for a specified city
    
    Args:
        city (str): The name of the city
        country (str, optional): The country code (e.g., 'US', 'UK')
    
    Returns:
        FunctionResponse: Contains success status and weather information
    """
    try:
        # This is a mock implementation. You would typically call a weather API here
        weather_info = {
            "temperature": "42°F",
            "condition": "Sunny",
            "humidity": "65%"
        }
        
        location = f"{city}, {country}" if country else city
        return FunctionResponse(
            success=True,
            message=f"Current weather in {location}: {weather_info['temperature']}, {weather_info['condition']}",
            data=weather_info
        )
    except Exception as e:
        return FunctionResponse(
            success=False,
            message=f"Failed to get weather information: {str(e)}"
        )

# Dictionary of available functions with their parameter schemas
AVAILABLE_FUNCTIONS = {
    "get_weather": {
        "function": get_weather,
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city"
                },
                "country": {
                    "type": "string",
                    "description": "The country code (e.g., 'US', 'UK')",
                    "optional": True
                }
            },
            "required": ["city"]
        }
    },
    "get_base_usdc_balance": {
        "function": get_base_usdc_balance,
        "parameters": {
            "type": "object",
            "properties": {},  # No parameters needed
            "required": []
        }
    },
    "send_usdc": {
        "function": send_usdc,
        "parameters": {
            "type": "object",
            "properties": {
                "to_address": {
                    "type": "string",
                    "description": "Ethereum address to send USDC to"
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of USDC to send"
                }
            },
            "required": ["to_address", "amount"]
        }
    }
}