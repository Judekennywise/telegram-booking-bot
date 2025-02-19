import os
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ContextTypes
)

load_dotenv()

import logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
#filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
# Configuration
DAYS_CONFIG_FILE = 'days_config.json'
APPOINTMENTS_FILE = 'appointments.json'

# Load days configuration
try:
    with open(DAYS_CONFIG_FILE, 'r') as f:
        days_config = json.load(f)
except FileNotFoundError:
    days_config = {
        'wednesday': {
            'active': True,
            'start': "11:00",
            'end': "16:00",
            'duration': 60,
            'breaks': []
        },
        'friday': {
            'active': True,
            'start': "11:00",
            'end': "15:00",
            'duration': 30,
            'breaks': [{'start': "13:00", 'end': "14:00"}]
        }
    }

# Modified appointments structure
appointments = {}  # Format: {user_id: {day: str, time: datetime, name: str, contact: str}}

# New conversation states
CHOOSE_DAY, GET_NAME, GET_CONTACT, CHOOSE_TIME = range(4)

# Admin commands
async def toggle_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command")
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"Wednesday {'✅' if days_config['wednesday']['active'] else '❌'}",
                callback_data='toggle_wednesday'
            ),
            InlineKeyboardButton(
                f"Friday {'✅' if days_config['friday']['active'] else '❌'}",
                callback_data='toggle_friday'
            )
        ]
    ]
    await update.message.reply_text(
        "Toggle booking days:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = query.data.split('_')[1]
    
    days_config[day]['active'] = not days_config[day]['active']
    with open(DAYS_CONFIG_FILE, 'w') as f:
        json.dump(days_config, f)
    
    await query.edit_message_text(
        text=f"✅ {day.capitalize()} availability toggled {'ON' if days_config[day]['active'] else 'OFF'}"
    )

async def cancel_booking_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command")
        return

    if not appointments:
        await update.message.reply_text("No active bookings")
        return

    buttons = []
    for user_id, booking in appointments.items():
        btn_text = (f"{booking['name']} - {booking['day']} "
                    f"{datetime.fromisoformat(booking['time']).strftime('%H:%M')}")
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"cancel_{user_id}")])
    
    await update.message.reply_text(
        "Select booking to cancel:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.data.split('_')[1]
    
    if user_id in appointments:
        # Cancel reminder
        jobs = context.job_queue.get_jobs_by_name(user_id)
        for job in jobs:
            job.schedule_removal()
        
        # Remove appointment
        del appointments[user_id]
        with open(APPOINTMENTS_FILE, 'w') as f:
            json.dump(appointments, f)
        
        await query.edit_message_text("✅ Booking cancelled")
        # Notify user
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Your booking has been cancelled by admin"
        )
    else:
        await query.edit_message_text("❌ Booking no longer exists")

SET_DURATION_DAY, SET_DURATION_VALUE = range(8, 10)
ADD_BREAK_DAY, ADD_BREAK_START, ADD_BREAK_END = range(10, 13)
REMOVE_BREAK_DAY, SELECT_BREAK_TO_REMOVE = range(13, 15)

# Add these admin command handlers
async def set_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command")
        return

    buttons = [
        [
            InlineKeyboardButton("Wednesday", callback_data="duration_wednesday"),
            InlineKeyboardButton("Friday", callback_data="duration_friday")
        ]
    ]
    await update.message.reply_text(
        "Select day to set slot duration:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SET_DURATION_DAY

async def set_duration_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['duration_day'] = query.data.split('_')[1]
    await query.edit_message_text("Enter new slot duration in minutes:")
    return SET_DURATION_VALUE

async def set_duration_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        duration = int(update.message.text)
        if duration <= 0:
            raise ValueError
        
        day = context.user_data['duration_day']
        days_config[day]['duration'] = duration
        
        with open(DAYS_CONFIG_FILE, 'w') as f:
            json.dump(days_config, f)
        
        await update.message.reply_text(
            f"✅ {day.capitalize()} slot duration set to {duration} minutes"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid duration. Please enter a positive integer")
        return SET_DURATION_VALUE

async def add_break(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command")
        return

    buttons = [
        [
            InlineKeyboardButton("Wednesday", callback_data="break_wednesday"),
            InlineKeyboardButton("Friday", callback_data="break_friday")
        ]
    ]
    await update.message.reply_text(
        "Select day to add break:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ADD_BREAK_DAY

async def add_break_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['break_day'] = query.data.split('_')[1]
    await query.edit_message_text("Enter break start time (HH:MM):")
    return ADD_BREAK_START

async def add_break_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text, "%H:%M")
        context.user_data['break_start'] = update.message.text
        await update.message.reply_text("Enter break end time (HH:MM):")
        return ADD_BREAK_END
    except ValueError:
        await update.message.reply_text("❌ Invalid time format. Use HH:MM")
        return ADD_BREAK_START

async def add_break_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        start = datetime.strptime(context.user_data['break_start'], "%H:%M")
        end = datetime.strptime(update.message.text, "%H:%M")
        
        if end <= start:
            raise ValueError("End time must be after start time")
        
        day = context.user_data['break_day']
        days_config[day]['breaks'].append({
            'start': context.user_data['break_start'],
            'end': update.message.text
        })
        
        with open(DAYS_CONFIG_FILE, 'w') as f:
            json.dump(days_config, f)
        
        await update.message.reply_text(
            f"✅ Break added to {day.capitalize()}: "
            f"{context.user_data['break_start']} - {update.message.text}"
        )
        return ConversationHandler.END
    except ValueError as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        return ADD_BREAK_END

async def remove_break(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only command")
        return
    
    buttons = [
        [
            InlineKeyboardButton("Wednesday", callback_data="removebreak_wednesday"),
            InlineKeyboardButton("Friday", callback_data="removebreak_friday")
        ]
    ]
    await update.message.reply_text(
        "Select day to remove break:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return REMOVE_BREAK_DAY

async def remove_break_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    day = query.data.split('_')[1]
    context.user_data['remove_break_day'] = day
    breaks = days_config[day]['breaks']
    
    if not breaks:
        await query.edit_message_text(
            f"❌ No breaks configured for {day.capitalize()}"
        )
        return ConversationHandler.END
    
    # Show list of breaks to remove
    buttons = [
        [InlineKeyboardButton(
            f"{b['start']} - {b['end']}", 
            callback_data=f"removebreak_{index}"
        )] 
        for index, b in enumerate(breaks)
    ]
    buttons.append([InlineKeyboardButton("Remove All", callback_data="removebreak_all")])
    
    await query.edit_message_text(
        f"Select break to remove from {day.capitalize()}:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECT_BREAK_TO_REMOVE

async def handle_break_removal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    day = context.user_data['remove_break_day']
    break_data = query.data.split('_')[1]
    
    try:
        if break_data == "all":
            days_config[day]['breaks'] = []
            message = "All breaks removed"
        else:
            index = int(break_data)
            removed_break = days_config[day]['breaks'].pop(index)
            message = f"Removed break {removed_break['start']} - {removed_break['end']}"
        
        with open(DAYS_CONFIG_FILE, 'w') as f:
            json.dump(days_config, f)
            
        await query.edit_message_text(f"✅ {message} from {day.capitalize()}")
        
    except (IndexError, ValueError) as e:
        await query.edit_message_text(f"❌ Error: Invalid break selection")
    finally:
        return ConversationHandler.END


# Modified booking flow
async def start(update: Update, context: CallbackContext):
    active_days = [day for day, config in days_config.items() if config['active']]
    if not active_days:
        await update.message.reply_text("❌ No available days for booking")
        return ConversationHandler.END

    buttons = []
    for day in active_days:
        buttons.append([InlineKeyboardButton(day.capitalize(), callback_data=day)])
    
    await update.message.reply_text(
        "Choose a day for your appointment:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CHOOSE_DAY

async def choose_day(update: Update, context: CallbackContext):
    query = update.callback_query
    day = query.data
    context.user_data['day'] = day
    await query.edit_message_text(text=f"Selected {day.capitalize()}\nPlease enter your full name:")
    return GET_NAME

async def get_name(update: Update, context: CallbackContext) -> int:
    context.user_data['name'] = update.message.text
    await update.message.reply_text("📞 Please enter your contact number:")
    return GET_CONTACT

async def get_contact(update: Update, context: CallbackContext) -> int:
    context.user_data['contact'] = update.message.text
    return await show_time_slots(update, context)

def generate_slots(day):
    config = days_config[day]
    today = datetime.today()
    
    # Get next occurrence of the selected day
    day_number = 2 if day == 'wednesday' else 4
    next_day = today + timedelta((day_number - today.weekday()) % 7)
    
    start = datetime.strptime(config['start'], "%H:%M")
    end = datetime.strptime(config['end'], "%H:%M")
    duration = timedelta(minutes=config['duration'])
    
    slots = []
    current = next_day.replace(
        hour=start.hour,
        minute=start.minute,
        second=0,
        microsecond=0
    )
    
    while current.time() <= end.time():
        # Check breaks
        in_break = False
        for b in config['breaks']:
            break_start = datetime.strptime(b['start'], "%H:%M").time()
            break_end = datetime.strptime(b['end'], "%H:%M").time()
            if break_start <= current.time() < break_end:
                current = current.replace(
                    hour=break_end.hour,
                    minute=break_end.minute
                )
                in_break = True
                break
        
        if not in_break:
            # Check availability
            slot_taken = any(
                app['day'] == day and 
                datetime.fromisoformat(app['time']) == current 
                for app in appointments.values()
            )
            if not slot_taken:
                slots.append(current)
            
            current += duration
    
    return slots

async def show_time_slots(update: Update, context: CallbackContext):
    day = context.user_data['day']
    slots = generate_slots(day)
    
    keyboard = [
        [InlineKeyboardButton(slot.strftime("%H:%M"), callback_data=slot.isoformat())]
        for slot in slots
    ]
    
    await update.message.reply_text(
        f"Available slots for {day.capitalize()}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_TIME

async def choose_time(update: Update, context: CallbackContext):
    query = update.callback_query
    time = query.data
    context.user_data['time'] = time
    user_id = query.from_user.id

    # Save appointment
    appointment = {
        'day': context.user_data['day'],
        'time': context.user_data['time'],
        'name': context.user_data['name'],
        'contact': context.user_data['contact']
    }
    appointments[user_id] = appointment
    # with open(APPOINTMENTS_FILE, 'w') as f:
    #     json.dump(appointments, f)

    chosen_time = datetime.fromisoformat(context.user_data['time'])

    

    confirmation_text = (
        "✅ Appointment confirmed!\n\n"
        f"📅 Date: {chosen_time.strftime("%A, %B %d at %I:%M %p")}\n"
        f"👤 Name: {context.user_data['name']}\n"
        f"📞 Contact: {context.user_data['contact']}\n\n"
        "You'll receive a reminder 24 hours before your appointment."
    )
    
    await query.edit_message_text(text=confirmation_text)
    # Notify admin
    admin_message = (
        f"New booking:\n"
        f"Name: {context.user_data['name']}\n"
        f"Contact: {context.user_data['contact']}\n"
        f"Day: {context.user_data['day']}\n"
        f"Time: {chosen_time.strftime("%A, %B %d at %I:%M %p")}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_message
    )
    # Schedule reminder
    reminder_time = datetime.fromisoformat(context.user_data['time']) - timedelta(hours=1)
    await context.job_queue.run_once(
        send_reminder,
        reminder_time,
        name=str(user_id),
        user_id=user_id,
        chat_id=user_id
    )
    return ConversationHandler.END

async def confirm_booking(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    # Save appointment
    appointment = {
        'day': context.user_data['day'],
        'time': context.user_data['time'],
        'name': context.user_data['name'],
        'contact': context.user_data['contact']
    }
    appointments[user_id] = appointment
    with open(APPOINTMENTS_FILE, 'w') as f:
        json.dump(appointments, f)

    # Schedule reminder
    reminder_time = datetime.fromisoformat(context.user_data['time']) - timedelta(hours=1)
    context.job_queue.run_once(
        send_reminder,
        reminder_time,
        name=str(user_id),
        user_id=user_id,
        chat_id=user_id
    )

    # Notify admin
    admin_message = (
        f"New booking:\n"
        f"Name: {context.user_data['name']}\n"
        f"Contact: {context.user_data['contact']}\n"
        f"Day: {context.user_data['day']}\n"
        f"Time: {context.user_data['time']}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_message
    )

    await query.edit_message_text("✅ Booking confirmed")
    await context.bot.send_message(
        chat_id=user_id,
        text="✅ Your booking is confirmed"
    )
    return ConversationHandler.END

async def send_reminder(context: CallbackContext):
    user_id = context.job.name
    await context.bot.send_message(
        chat_id=user_id,
        text="⏰ Reminder: Your booking is in 1 hour"
    )

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Booking cancelled", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# Modified main function
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Admin handlers
    application.add_handler(CommandHandler('toggle_days', toggle_day))
    application.add_handler(CommandHandler('cancel_booking', cancel_booking_admin))
    application.add_handler(CallbackQueryHandler(handle_toggle, pattern=r"^toggle_"))
    application.add_handler(CallbackQueryHandler(handle_admin_cancel, pattern=r"^cancel_"))
    duration_handler = ConversationHandler(
        entry_points=[CommandHandler('set_duration', set_duration)],
        states={
            SET_DURATION_DAY: [CallbackQueryHandler(set_duration_day)],
            SET_DURATION_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_duration_value)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    break_handler = ConversationHandler(
        entry_points=[CommandHandler('add_break', add_break)],
        states={
            ADD_BREAK_DAY: [CallbackQueryHandler(add_break_day)],
            ADD_BREAK_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_break_start)],
            ADD_BREAK_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_break_end)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(duration_handler)
    application.add_handler(break_handler)

    remove_break_handler = ConversationHandler(
    entry_points=[CommandHandler('remove_break', remove_break)],
    states={
        REMOVE_BREAK_DAY: [CallbackQueryHandler(remove_break_day, pattern=r"^removebreak_")],
        SELECT_BREAK_TO_REMOVE: [CallbackQueryHandler(handle_break_removal, pattern=r"^removebreak_")]
    },
    fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(remove_break_handler)

    # Booking conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSE_DAY: [CallbackQueryHandler(choose_day)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_contact)],
            CHOOSE_TIME: [CallbackQueryHandler(choose_time)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()