from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sse_starlette import EventSourceResponse
import settings
import views
import time
import logging
import asyncio
import uuid
from threading import Lock
import redis
import json
import uvicorn
import sqlite3
from uuid import uuid4
from urllib.parse import urlparse, parse_qs
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse
from socket import gethostname
import aihub.LLM_response as gpt
# 基本配置相關#######################################################################
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# 創建 FastAPI 應用程式並配置 session middleware
app = FastAPI()

#app.add_middleware(CustomMiddleware)

app.add_middleware(SessionMiddleware, secret_key='test123')

app.mount("/static", StaticFiles(directory="static"), name="static")

# python變數傳入html配置
templates = Jinja2Templates(directory="templates")

# 使用字典存儲每個使用者的輸出，以 session ID 為鍵
# 為模擬chain of thought
node_outputs = {}
node_outputs_lock = asyncio.Lock()

# redis儲存相關，針對schema，因為schema資料量過多無法存在fastapi的session中
memory_store = {}
memory_store_lock = Lock()  # 每次存取都有對應的key，使用同步的 threading.Lock

# sqllite path
sqllite_path = './db/'


def is_redis_available():
    """檢查 Redis 是否可用"""
    if redis_client is None:
        return False
    try:
        return redis_client.ping()
    except:
        return False


def is_ajax(request: Request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


# redis相關操作 #######################################################################
def get_from_redis_or_memory(key, default=None):
    """從 Redis 或內存獲取數據，帶回退機制"""
    if is_redis_available():
        try:
            value = redis_client.get(key)
            if value:
                if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                    return json.loads(value)
                return value
            return default
        except Exception as e:
            logger.error(f"從 Redis 讀取錯誤 ({key}): {str(e)}")

    # Redis 不可用，使用內存存儲
    with memory_store_lock:
        return memory_store.get(key, default)


def save_to_redis_or_memory(key, value, expire=86400):
    """保存數據到 Redis 或內存，帶回退機制"""
    if isinstance(value, dict) or isinstance(value, list):
        serialized = json.dumps(value)
    else:
        serialized = value

    if is_redis_available():
        try:
            redis_client.set(key, serialized)
            if expire > 0:
                redis_client.expire(key, expire)
            return True
        except Exception as e:
            logger.error(f"保存到 Redis 錯誤 ({key}): {str(e)}")

    # Redis 不可用，使用內存存儲
    with memory_store_lock:
        memory_store[key] = value
        return True


def delete_from_redis_or_memory(key):
    """從 Redis 或內存刪除數據，帶回退機制"""
    if is_redis_available():
        try:
            redis_client.delete(key)
            redis_client.execute_command("MEMORY PURGE")
        except Exception as e:
            logger.error(f"從 Redis 刪除錯誤 ({key}): {str(e)}")

    # 從內存中移除
    with memory_store_lock:
        if key in memory_store:
            del memory_store[key]


def clear_redis_and_memory():
    """清空 Redis 與內存中的所有數據"""
    if is_redis_available():
        try:
            # 若只想清空目前資料庫，使用 flushdb；若要清空所有資料庫，可改用 flushall
            redis_client.flushdb()
        except Exception as e:
            logger.error(f"清空 Redis 失敗: {str(e)}")

    # 清空內存中的所有數據
    with memory_store_lock:
        memory_store.clear()


# sql lite相關 #######################################################################

def sqllite_insert(db_table, data):
    conn = sqlite3.connect(fr"{sqllite_path}FCT_MESSAGE_HISTORY.db")
    cursor = conn.cursor()

    # 預防table lock問題
    cursor.execute("PRAGMA journal_mode=WAL;")

    sql = fr'''
    INSERT INTO {db_table} (
        session_id, session_schema, session_query, session_result, 
        date, time, user_input, query_schema, 
        output_sql, reoutput_sql, output_result, result_sql,status, table_name ,
        data_market_no , 
        index_id, username, hostname
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    cursor.execute(sql, data)
    conn.commit()
    conn.close()


# fast api相關 #######################################################################

# 首頁初始化相關
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):

    user_info = {'username': 'guest', 'hostname': 'localhost'}

    print(f"新訪問 - 使用者: {(user_info['username'] + user_info['hostname']).replace('-', '')}")
    logger.info(f"新訪問 - 使用者: {user_info['username']}")

    request.session['user_id'] = (user_info['username'] + user_info['hostname']).replace('-', '')

    conn = sqlite3.connect(fr"{sqllite_path}FCT_MESSAGE_HISTORY.db")
    cursor = conn.cursor()
    cursor.execute(fr'''
        CREATE TABLE IF NOT EXISTS {request.session['user_id']} (
            session_id TEXT,
            session_schema TEXT,
            session_query TEXT,
            session_result TEXT,
            date TEXT,
            time TEXT,
            user_input TEXT,
            query_schema TEXT,
            output_sql TEXT,
            reoutput_sql TEXT,
            output_result TEXT,
            result_sql TEXT,
            status TEXT,
            table_name TEXT,
            data_market_no TEXT,
            index_id INTEGER,
            username TEXT,
            hostname TEXT
        )
    ''')
    conn.commit()

    # 儲存使用者資訊到 session
    request.session['user_info'] = {
        'username': user_info['username'],
        'hostname': user_info['hostname'],
        'user_str': (user_info['username'] + user_info['hostname']).replace('-', '')
    }

    # 初始化該使用者的輸出列表
    async with node_outputs_lock:
        node_outputs[request.session['user_id']] = []

    # 存儲 session IDs
    user_id = request.session['user_id']
    request.session['session_key'] = str(uuid.uuid4())
    request.session['session_id_schema_query'] = gpt.session_id(settings.api_key)
    request.session['session_id_table_query'] = gpt.session_id(settings.api_key)
    request.session['session_id_table_answer'] = gpt.session_id(settings.api_key)
    request.session['session_id_table_chart'] = gpt.session_id(settings.api_key)
    request.session['append_token'] = 0
    # 初始化 Redis/內存中的聊天歷史
    print('user_id:', user_id)
    delete_from_redis_or_memory(user_id)
    save_to_redis_or_memory(f"chat_history:{user_id}", [])

    # 從資料庫或其他來源取得表格清單
    tables = views.get_tables()

    # 將 tables 傳入 index.html 模板
    return templates.TemplateResponse('index.html', {"request": request, "tables": tables})


# 接收前端使用者輸入，執行text to sql並回復
@app.post("/api/message")
async def handle_message(request: Request):
    user_id = request.session.get('user_id')
    session_key = request.session.get('session_key')
    user_info = request.session.get('user_info')

    logger.info(f"使用者 {user_info['user_str']} (session_id: {user_id}) 開始處理訊息")

    # 清空當前使用者的輸出列表
    async with node_outputs_lock:
        node_outputs[user_id] = []

    data = await request.json()
    user_input = data.get('message', '')
    if not user_input:
        return JSONResponse(content={'error': 'No message provided'}, status_code=400)

    # 取得 各chat session
    session_id_schema_query = request.session.get('session_id_schema_query')
    session_id_table_query = request.session.get('session_id_table_query')
    session_id_table_answer = request.session.get('session_id_table_answer')

    # 取得使用者選擇的表格相關資訊
    DATAMARKET_NO = request.session.get('DATAMARKET_NO')
    table_name = request.session.get('table_name')
    OWNER_SCHEMA = request.session.get('OWNER_SCHEMA')
    append_token = request.session.get('append_token', 0)
    # 從 Redis 或內存中獲取 table_schema
    schema_key = f"schema:{user_id}:{DATAMARKET_NO}"
    table_comment_key = f"table_comment:{user_id}:{DATAMARKET_NO}"
    table_schema = get_from_redis_or_memory(schema_key)
    table_comment = get_from_redis_or_memory(table_comment_key)
    print(f"設置後的 session: {request.session}")
    # print('輸入', table_schema)
    # print('輸入', table_name)
    # print('輸入', DATAMARKET_NO)

    # 初始化 state
    initial_state = {
        "user_input": user_input,
        "DATAMARKET_NO": DATAMARKET_NO,
        "question_type": "",
        "table_name": table_name,
        "table_schema": table_schema,
        "table_comment": table_comment,
        "OWNER_SCHEMA": OWNER_SCHEMA,
        "raw_table_schema": table_schema,
        "session_id_schema_query": session_id_schema_query,
        "session_id_table_query": session_id_table_query,
        "session_id_table_answer": session_id_table_answer,
        "sql_query": "",
        "query_result": "",
        "final_message": "",
        "status": "",
        "append_token": append_token
    }

    # 非同步處理並將每一步的 output 加入使用者特定的輸出列表
    logger.info(f"使用者 {user_info['user_str']} - 開始過濾 問題")
    state = await asyncio.to_thread(views.filter_question, initial_state)

    logger.info(f"使用者 {user_info['user_str']} - 開始過濾 schema")
    state, outputschema = await asyncio.to_thread(views.filter_schema, initial_state)
    async with node_outputs_lock:
        node_outputs[user_id].append(outputschema)

    logger.info(f"使用者 {user_info['user_str']} - 開始生成 SQL")
    state, outputsql = await asyncio.to_thread(views.generate_sql, state)
    async with node_outputs_lock:
        node_outputs[user_id].append(outputsql)

    logger.info(f"使用者 {user_info['user_str']} - 開始執行 SQL")
    state = await asyncio.to_thread(views.execute_sql, state)

    try:
        logger.info(f"使用者 {user_info['user_str']} - 嘗試重新執行 SQL")
        state, reoutputsql = await asyncio.to_thread(views.re_execute_sql, state)
        async with node_outputs_lock:
            node_outputs[user_id].append(reoutputsql)
    except Exception as e:
        reoutputsql = ''
        logger.info(f"使用者 {user_info['user_str']} - SQL 已正確，跳出執行: {str(e)}")
        pass

    logger.info(f"使用者 {user_info['user_str']} - 開始分析結果")
    state,append_token = await asyncio.to_thread(views.analyze_result, state)

    request.session['append_token'] = append_token

    # 構建回應
    response = {
        'message': state["final_message"],
        'sql_query': state["sql_query"],
        'status': state["status"]
    }

    # 從 Redis 獲取聊天歷史
    chat_history_key = f"chat_history:{user_id}"
    chat_history = get_from_redis_or_memory(chat_history_key, [])

    # 創建新的聊天記錄
    # chat_record = {
    #     'message': response.get('message'),
    #     'sql_query': response.get('sql_query'),
    #     'status': response.get('status')
    # }

    # 如果成功，添加到歷史記錄
    chat_index = -1
    if response.get('status') == 'success':
        chat_history.append(response)
        chat_index = len(chat_history) - 1

        # 一次性保存多個值到 Redis
        if is_redis_available():
            try:
                pipe = redis_client.pipeline()
                pipe.set(chat_history_key, json.dumps(chat_history))
                pipe.expire(chat_history_key, 86400)
                pipe.set(f"current_sql_query:{user_id}", response.get('sql_query', ''))
                pipe.expire(f"current_sql_query:{user_id}", 86400)
                pipe.execute()
            except Exception as e:
                logger.error(f"Redis 管道操作錯誤: {str(e)}")
                # 回退到單獨保存
                save_to_redis_or_memory(chat_history_key, chat_history)
                save_to_redis_or_memory(f"current_sql_query:{user_id}", response.get('sql_query', ''))
        else:
            # Redis 不可用，保存到內存
            save_to_redis_or_memory(chat_history_key, chat_history)
            save_to_redis_or_memory(f"current_sql_query:{user_id}", response.get('sql_query', ''))

    insert_datas = (session_key, session_id_schema_query, session_id_table_query, session_id_table_answer,
                    time.strftime("%Y-%m-%d"), time.strftime("%H:%M:%S"), user_input, outputschema,
                    outputsql, reoutputsql, state["final_message"], state["sql_query"], response.get('status'),
                    table_name, DATAMARKET_NO,
                    chat_index, user_info['username'], user_info['hostname'])
    sqllite_insert(user_id, insert_datas)

    # 回傳 JSON，包含機器人的回覆、 SQL 查詢語句以及該聊天記錄的索引
    return JSONResponse(content={
        'response': response.get('message').replace('#', '').replace('*', ''),
        'sql': response.get('sql_query'),
        'chat_index': chat_index,
        'status': response.get('status')
    })


# 產生圖表
@app.get("/api/charts")
async def get_charts(request: Request):
    user_id = request.session.get('user_id')
    session_id_table_chart = request.session.get('session_id_table_chart')

    # 從 Redis 或內存中獲取當前消息和 SQL 查詢
    user_input = get_from_redis_or_memory(f"current_message:{user_id}", "")
    step4_response_transform = get_from_redis_or_memory(f"current_sql_query:{user_id}", "")

    # charts_data = views.generate_charts(session_id_table_chart, step4_response_transform, user_input)
    charts_data = []
    return JSONResponse(content={'charts': charts_data})


# 選取table
@app.post("/select_table")
async def select_table(request: Request):
    data = await request.json()
    DATAMARKET_NO = data.get('tableName', None)
    table_schema, table_name, OWNER_SCHEMA, table_comment = views.get_table_schema(DATAMARKET_NO)

    # 將必要的識別符存儲在 session 中
    request.session['DATAMARKET_NO'] = DATAMARKET_NO
    request.session['table_name'] = table_name
    request.session['OWNER_SCHEMA'] = OWNER_SCHEMA

    # 生成唯一的鍵並存儲 table_schema
    user_id = request.session.get('user_id')
    schema_key = f"schema:{user_id}:{DATAMARKET_NO}"
    table_comment_key = f"table_comment:{user_id}:{DATAMARKET_NO}"
    # 存儲到 Redis
    success = save_to_redis_or_memory(schema_key, table_schema, 86400)
    save_to_redis_or_memory(table_comment_key, table_comment, 86400)

    if success:
        print("使用者 datamarket no:", DATAMARKET_NO)
        print("使用者選擇了 table_name:", table_name)
        print(f"Schema 已存儲，key: {schema_key}")

        # 回應前端已選擇的表格
        return JSONResponse(content={"status": "OK", "selectedTable": table_name})
    else:
        return JSONResponse(content={"status": "error", "message": "無法存儲表格資訊"}, status_code=500)


# 下載 SQL 查詢結果
@app.get("/download_sql")
async def download_sql(request: Request, chat_index: str = ""):
    user_id = request.session.get('user_id')

    # 先取得 chat_index 參數原始字串
    chat_index_str = chat_index
    print('chat_index string:', chat_index_str)

    # 如果 chat_index 為空或等於 "undefined"，就回傳錯誤
    if not chat_index_str or chat_index_str == 'undefined':
        return JSONResponse(content={'error': 'chat_index parameter is required or invalid'}, status_code=400)

    try:
        chat_index = int(chat_index_str)
    except ValueError:
        return JSONResponse(content={'error': 'chat_index must be an integer'}, status_code=400)

    # 從 Redis 或內存獲取聊天歷史
    chat_history_key = f"chat_history:{user_id}"
    chat_history = get_from_redis_or_memory(chat_history_key, [])

    print('len(chat_history):', len(chat_history))
    if chat_index < 0 or chat_index >= len(chat_history):
        return JSONResponse(content={'error': 'Invalid chat_index'}, status_code=400)

    sql = chat_history[chat_index]['sql_query']
    csv_data = views.export_current_query_to_csv(sql)
    response = Response(content=csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=results.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


# 前端顯示模擬chain of though
@app.get("/stream_node_outputs")
async def stream_node_outputs(request: Request):
    """SSE 路由：持續監聽特定使用者的輸出並推送給前端"""
    # 在生成器函數開始前獲取用戶 ID
    user_id = request.session.get('user_id')

    if not user_id:
        return JSONResponse(content={"error": "No user ID found in session"}, status_code=400)

    # 確保該用戶在字典中有記錄
    async with node_outputs_lock:
        if user_id not in node_outputs:
            node_outputs[user_id] = []

    async def event_stream():
        nonlocal user_id
        last_len = 0
        try:
            while True:
                async with node_outputs_lock:
                    user_output = node_outputs.get(user_id, [])
                    if len(user_output) == 0:
                        last_len = 0
                    if len(user_output) > last_len:
                        new_data = user_output[last_len:]
                        last_len = len(user_output)
                        for item in new_data:
                            lines = item.replace('*', '').split("\n")
                            data_payload = "\n".join([f"{line}" for line in lines])
                            yield f"{data_payload}\n\n"

                await asyncio.sleep(1)
        except GeneratorExit:
            # 當客戶端斷開連接時清理資源
            pass

    return EventSourceResponse(event_stream())


# 前端顯示當前使用者相關資訊
@app.get("/api/current_user")
async def get_current_user(request: Request):
    user_info = request.session.get('user_info')
    if not user_info:
        raise HTTPException(status_code=400, detail="User ID not found")

    safe_info = {
        'username': user_info.get('username'),
        'hostname': user_info.get('hostname')
    }

    print(user_info)

    return JSONResponse(safe_info)


# 初始化清除快取
@app.get("/static/js/script.js")
async def serve_script():
    content = open("static/js/script.js", "r").read()
    response = Response(content=content, media_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0",port = 8080)

