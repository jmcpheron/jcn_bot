from web3 import Web3
from eth_account import Account
import os
from decimal import Decimal
from typing import NamedTuple, Optional

class TransactionResult(NamedTuple):
    success: bool
    message: str
    tx_hash: Optional[str] = None

class USDCTransactionHandler:
    def __init__(self):
        # Initialize Web3 with Base network
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('BASE_RPC_URL')))
        
        # USDC contract details for Base
        self.usdc_address = os.getenv('USDC_CONTRACT_ADDRESS')
        self.usdc_abi = [
            # ERC20 transfer function
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            },
            # balanceOf function
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Load bot's wallet
        self.private_key = os.getenv('BOT_PRIVATE_KEY')
        if not self.private_key:
            raise ValueError("BOT_PRIVATE_KEY not set in environment variables")
        
        self.account = Account.from_key(self.private_key)
        self.usdc_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.usdc_address),
            abi=self.usdc_abi
        )

    async def get_balance(self) -> TransactionResult:
        """Get the current USDC balance of the bot's wallet"""
        try:
            balance = self.usdc_contract.functions.balanceOf(
                self.account.address
            ).call()
            
            # Convert from wei (6 decimals for USDC)
            balance_decimal = Decimal(balance) / Decimal(10 ** 6)
            
            return TransactionResult(
                success=True,
                message=f"Current USDC balance on Base: {balance_decimal} USDC"
            )
        except Exception as e:
            return TransactionResult(
                success=False,
                message=f"Failed to get balance: {str(e)}"
            )

    async def send_usdc(self, to_address: str, amount: float) -> TransactionResult:
        """
        Send USDC to a specified address
        
        Args:
            to_address: The recipient's Ethereum address
            amount: Amount of USDC to send
        """
        try:
            # Validate address
            if not Web3.is_address(to_address):
                return TransactionResult(
                    success=False,
                    message="Invalid Ethereum address"
                )
            
            # Convert amount to wei (USDC has 6 decimals)
            amount_wei = int(amount * 10 ** 6)
            
            # Check balance
            balance = self.usdc_contract.functions.balanceOf(
                self.account.address
            ).call()
            
            if balance < amount_wei:
                return TransactionResult(
                    success=False,
                    message="Insufficient USDC balance"
                )
            
            # Prepare transaction
            transaction = self.usdc_contract.functions.transfer(
                self.w3.to_checksum_address(to_address),
                amount_wei
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 100000,  # Estimate gas limit
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(
                transaction, 
                self.private_key
            )
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                return TransactionResult(
                    success=True,
                    message=f"Successfully sent {amount} USDC",
                    tx_hash=tx_hash.hex()
                )
            else:
                return TransactionResult(
                    success=False,
                    message="Transaction failed",
                    tx_hash=tx_hash.hex()
                )
                
        except Exception as e:
            return TransactionResult(
                success=False,
                message=f"Transaction failed: {str(e)}"
            )

# Add to custom_functions.py:
AVAILABLE_FUNCTIONS = {
    "get_balance": {
        "function": USDCTransactionHandler().get_balance,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "send_usdc": {
        "function": USDCTransactionHandler().send_usdc,
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