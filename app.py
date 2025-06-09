from flask import Flask, request, session, redirect, render_template
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatRequest
from telethon.tl.types import User
import asyncio

app = Flask(__name__)
app.secret_key = 'secret_key_here'  # Change in production

API_ID = 28593211
API_HASH = "27ad7de4fe5cab9f8e310c5cc4b8d43d"

@app.route('/')
def home():
    if 'session' in session:
        return redirect('/channels')
    return render_template('home.html')

@app.route('/send_code', methods=['POST'])
def send_code():
    phone = request.form['phone']
    session['phone'] = phone

    async def send_code_request():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        code = await client.send_code_request(phone)
        session['code_hash'] = code.phone_code_hash
        session['session_str'] = client.session.save()
        await client.disconnect()
        return render_template('code_sent.html')
    
    return asyncio.run(send_code_request())

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        phone = session['phone']
        code = request.form['code']
        password = request.form.get('password')

        async def sign_in():
            client = TelegramClient(StringSession(session['session_str']), API_ID, API_HASH)
            await client.connect()
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=session['code_hash'])
            except SessionPasswordNeededError:
                if not password:
                    await client.disconnect()
                    return render_template('verify_password.html')
                await client.sign_in(password=password)

            me = await client.get_me()
            session_string = client.session.save()
            session['session'] = session_string
            session['user'] = {
                'username': me.username or "N/A",
                'id': me.id,
                'phone': phone
            }
            await client.disconnect()
            return render_template('login_success.html', 
                                  user=session['user'],
                                  api_id=API_ID,
                                  api_hash=API_HASH,
                                  session_string=session_string)

        return asyncio.run(sign_in())
    
    return render_template('verify_code.html')

@app.route('/channels')
def channels():
    if 'session' not in session:
        return redirect('/')
    
    string = session.get("session")
    user = session.get('user', {})

    async def list_entities():
        client = TelegramClient(StringSession(string), API_ID, API_HASH)
        await client.connect()
        
        channels = []
        groups = []
        bots = []
        
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if dialog.is_channel:
                if getattr(entity, 'broadcast', False):
                    # Broadcast channel
                    channels.append({
                        'id': entity.id,
                        'name': dialog.name,
                        'username': entity.username or 'Private',
                        'type': 'channel'
                    })
                elif getattr(entity, 'megagroup', False):
                    # Mega group
                    groups.append({
                        'id': entity.id,
                        'name': dialog.name,
                        'username': entity.username or 'Private',
                        'type': 'group'
                    })
            elif isinstance(entity, User) and entity.bot:
                # Bot
                bots.append({
                    'id': entity.id,
                    'name': dialog.name,
                    'username': entity.username or 'Private',
                    'type': 'bot'
                })
        
        await client.disconnect()
        return render_template('channels.html',
                              user=user,
                              channels=channels,
                              groups=groups,
                              bots=bots)
    
    return asyncio.run(list_entities())

@app.route('/leave', methods=['POST'])
def leave():
    if 'session' not in session:
        return redirect('/')
    
    string = session.get("session")
    entity_id = int(request.form['entity_id'])
    entity_type = request.form['entity_type']

    async def process_leave():
        client = TelegramClient(StringSession(string), API_ID, API_HASH)
        await client.connect()
        try:
            if entity_type in ['channel', 'group']:
                await client(LeaveChannelRequest(entity_id))
                result = "Left successfully."
            elif entity_type == 'bot':
                await client(DeleteChatRequest(entity_id))
                result = "Bot deleted successfully."
        except Exception as e:
            result = f"Error: {str(e)}"
        await client.disconnect()
        return render_template('action_result.html', result=result)
    
    return asyncio.run(process_leave())

@app.route('/leave_all', methods=['POST'])
def leave_all_entities():
    if 'session' not in session:
        return redirect('/')
    
    string = session.get("session")

    async def process_leave_all():
        client = TelegramClient(StringSession(string), API_ID, API_HASH)
        await client.connect()
        
        results = {
            'channels': {'success': 0, 'failed': 0},
            'groups': {'success': 0, 'failed': 0},
            'bots': {'success': 0, 'failed': 0}
        }
        
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            try:
                if dialog.is_channel:
                    if getattr(entity, 'broadcast', False):
                        await client(LeaveChannelRequest(entity.id))
                        results['channels']['success'] += 1
                    elif getattr(entity, 'megagroup', False):
                        await client(LeaveChannelRequest(entity.id))
                        results['groups']['success'] += 1
                elif isinstance(entity, User) and entity.bot:
                    await client(DeleteChatRequest(entity.id))
                    results['bots']['success'] += 1
            except Exception:
                if dialog.is_channel:
                    if getattr(entity, 'broadcast', False):
                        results['channels']['failed'] += 1
                    elif getattr(entity, 'megagroup', False):
                        results['groups']['failed'] += 1
                elif isinstance(entity, User) and entity.bot:
                    results['bots']['failed'] += 1
        
        await client.disconnect()
        return render_template('leave_all_result.html', results=results)
    
    return asyncio.run(process_leave_all())

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True)
