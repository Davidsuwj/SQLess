from flask import Flask, render_template, request, jsonify, session
import time
import settings
import views
import LLM_response as llm
from langchain.memory import ConversationBufferMemory
import sql_query
import json
from uuid import uuid4
import threading
app = Flask(__name__)
app.secret_key = 'test123'  

# 全域變數，用於儲存對話記憶
conversation_memories = {}

# 建立一個全域鎖，確保多線程環境下的資料操作同步
conversation_lock = threading.Lock()


@app.before_request
def load_conversation():
    # 如果 session 中沒有 conversation_id，就產生一個新的 UUID
    if 'conversation_id' not in session:
        session['conversation_id'] = str(uuid4())
    conv_id = session['conversation_id']

    # 使用鎖來保護對 conversation_memories 的存取
    with conversation_lock:
        if conv_id not in conversation_memories:
            conversation_memories[conv_id] = {
                'table_query': ConversationBufferMemory(return_messages=True),
                'table_answer': ConversationBufferMemory(return_messages=True),
                'table_chart': ConversationBufferMemory(return_messages=True)
            }

@app.route('/')
def home():
    print(settings.API_KEY)

    # 從資料庫或其他來源取得表格清單（請依據實際情況修改）
    #tables = views.get_tables()
    tables = ['1','2']

    # 將 tables 傳入 index.html 模板
    return render_template('index.html', tables=tables)

@app.route('/api/message', methods=['POST'])
def handle_message():
    data = request.get_json()
    user_input = data.get('message', '')
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400

    # 取得 session 中相關的識別碼
    #session_id_tablename = session.get('session_id_tablename')
    session_id_table_query = session.get('session_id_table_query')
    session_id_table_answer = session.get('session_id_table_answer')

    # 取得使用者選擇的表格相關資訊
    table_schema = session.get('table_schema')
    table_name = session.get('table_name')


    # 呼叫 views.execute 處理使用者輸入，返回的結果包含 message 與 sql_query
    response = views.execute(
        user_input,
        table_name,
        table_schema,
        session_id_table_query,
        session_id_table_answer
    )

    # 將結果存入 session（後續可能用於圖表或其他用途）
    session['current_sql_query'] = response.get('sql_query')
    session['current_message'] = response.get('message')

    # 回傳 JSON，包含機器人的回覆以及 SQL 查詢語句
    return jsonify({
        'response': response.get('message'),
        'sql': response.get('sql_query')
    })

@app.route('/api/charts')
def get_charts():
    user_input = session.get('current_message')
    session_id_table_chart = session.get('session_id_table_chart')
    step4_response_transform = session.get('current_sql_query')
    charts_data = views.generate_charts(session_id_table_chart, step4_response_transform, user_input)
    return jsonify({'charts': charts_data})

@app.route('/api/new_session', methods=['POST'])
def reset_session():
    #session['session_id_tablename'] = ConversationBufferMemory(return_messages=True)
    session['session_id_table_query'] = ConversationBufferMemory(return_messages=True)
    session['session_id_table_answer'] = ConversationBufferMemory(return_messages=True)
    session['session_id_table_chart'] = ConversationBufferMemory(return_messages=True)
    return jsonify({
        #'session_id_tablename': session['session_id_tablename'],
        'session_id_table_query': session['session_id_table_query'],
        'session_id_table_answer': session['session_id_table_answer'],
        'session_id_table_chart': session['session_id_table_chart']
    })

@app.route('/select_table', methods=['POST'])
def select_table():
    data = request.get_json()
    table_schema, table_name = views.get_table_schema(table_name)
    #table_name = ['1']
    #table_schema = ['1']
    session['table_schema'] = table_schema
    session['table_name'] = table_name
    
    print("使用者選擇了 table_name:", table_name)
    # 回應前端已選擇的表格
    return jsonify({"status": "OK", "selectedTable": table_name})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)