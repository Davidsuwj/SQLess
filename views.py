
import json
import pandas as pd
from datetime import datetime as dt
from typing import TypedDict
import oracle_query
import settings
from fastapi import Request
from flask import Flask, render_template, request
import requests
import tiktoken
import aihub.LLM_response as gpt

def token_count(text):
    encoder = tiktoken.encoding_for_model(settings.model)
    tokens = encoder.encode(text)
    return len(tokens)

def json_to_markdown(json_data):

    if isinstance(json_data, pd.DataFrame):
        json_data = json_data.fillna("").to_dict(orient='records')
    
    if not json_data:
        return ""

    headers = json_data[0].keys()
    md = f"| {' | '.join(headers)} |\n"
    md += f"| {' | '.join(['---'] * len(headers))} |\n"
    
    for row in json_data:
        md += "| " + " | ".join(str(row.get(h, "") or "") for h in headers) + " |\n"
    
    return md

def export_current_query_to_csv(sql):
    data = oracle_query.sql_query(sql.replace('FETCH FIRST 1000 ROWS ONLY', ''))
    try:
        rows = json.loads(data)
    except Exception as e:
        raise ValueError("無法解析查詢結果的 JSON 格式: " + str(e))
    df = pd.DataFrame(rows)
    csv_data = df.to_csv(encoding='utf-8', index=False)
    return csv_data

def get_tables():
    table = oracle_query.sql_query('''SELECT DATAMARKET_NO,TABLE_NAME,MAPPING FROM table''')
    data = json.loads(table)
    df = pd.DataFrame(data)
    return df['DATAMARKET_NO'].to_list()

def get_table_schema(table_id: str) -> tuple[str, str, str, str]:
    try:
        table_name_query = f"""SELECT distinct TABLE_NAME,OWNER_SCHEMA,TABLE_COMMENT FROM table WHERE DATAMARKET_NO = '{table_id}'"""
        table_result = json.loads(oracle_query.sql_query(table_name_query))
        table_name = pd.DataFrame(table_result)['TABLE_NAME'].iloc[0]
        OWNER_SCHEMA = pd.DataFrame(table_result)['OWNER_SCHEMA'].iloc[0]
        table_comment = pd.DataFrame(table_result)['TABLE_COMMENT'].iloc[0]
        schema_query = f"""SELECT COLUMN_NAME, DATA_TYPE, COLUMN_COMMENT,COLUMN_LOGIC FROM table WHERE TABLE_NAME = '{table_name}' """
        schema_result = json.loads(oracle_query.sql_query(schema_query))
        schema_df = pd.DataFrame(schema_result)
        schema = schema_df.to_dict(orient='records')
        return schema, table_name, OWNER_SCHEMA,table_comment
    except Exception as e:
        return None, None

def generate_charts(session_id_table_chart, step4_response_transform, user_input):
    api_key = settings.api_key
    version = settings.version
    service = settings.service
    table_find = oracle_query.sql_query(fr'''{step4_response_transform}''')
    print('圖表繪製:', user_input)
    
    if len(table_find) > 1000:
        return []
    else:
        question = fr'''
    根據{table_find}這邊的資料，與user的問題跟需求:{user_input}，給我一個有apple質感的python圖表，

    使用matplotlib繪製，請用以下模板，將代碼填入，中文必須為繁體中文，不要講任何話：

    import matplotlib
    matplotlib.use('Agg')  # 設置後端為Agg（非互動式）
    import matplotlib.pyplot as plt
    import pandas as pd
    import io
    import base64

    # 設置中文字體
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False

    # 你的數據處理和繪圖代碼

    # 保存為base64字符串
    img_stream = io.BytesIO()
    plt.savefig(img_stream, format='png', bbox_inches='tight', dpi=300)
    img_stream.seek(0)
    img_base64 = base64.b64encode(img_stream.getvalue()).decode('utf-8')
    plt.close('all')

    # 請務必在最後加上這行，才能被外部取得：
    result = img_base64
    '''
        output = gpt.chat_response(api_key, session_id_table_chart,service, version, 'normal', question)
        output = output.replace('```python', '').replace('```', '')
        
        try:
            local_dict = {}
            exec(output, globals(), local_dict)
            if 'result' in local_dict:
                return [{
                    'type': 'image',
                    'data': f"data:image/png;base64,{local_dict['result']}"
                }]
            else:
                print('No image data generated (result not found).')
                return []
        except Exception as e:
            print(f"Error executing chart code: {str(e)}")
            return []



def log_sql_operation(SESSION_KEY: str, step: str, retry: int, user_input: str, ai_output: str) -> None:
    log_statement = fr"""
    INSERT INTO RECORD(CREATE_DATE,SESSION_KEY , STEPS, RETRY_TIMES, USER_INPUT, AI_OUTPUT)
    VALUES(SYSDATE,'{SESSION_KEY}', '{step}', {retry}, TO_CLOB('{user_input.replace(",", "").replace("'", "''")}'),
    TO_CLOB('{ai_output.replace(",", "").replace("'", "''")}'))
    """
    oracle_query.sql_query(log_statement)

def safe_check_sql(sql: str) -> bool:
    """Check if SQL contains banned operations (DELETE or INSERT)."""
    try:
        lower_sql = sql.lower()
        if "delete" in lower_sql or "insert" in lower_sql:
            return False
        return True
    except Exception as e:
        print(f"SQL 內容檢查失敗: {e}")
        return False

def llm_response(api_key: str, session_id: str, version: str, prompt_type: str, prompt: str) -> str:
    service = settings.service
    return gpt.chat_response(api_key, session_id,service, version, prompt_type, prompt)

def sqlquery(sql: str) -> str:
    """Execute an Oracle SQL query."""
    return oracle_query.sql_query(sql)

##########################################################################################################
class MyState(TypedDict):
    user_input: str
    DATAMARKET_NO: str
    question_type: str
    table_name: str
    table_schema: str
    table_comment: str
    OWNER_SCHEMA: str
    raw_table_schema: str
    session_id_schema_query: str
    session_id_table_query: str
    session_id_table_answer: str
    sql_query: str
    query_result: str
    final_message: str
    status: str #check
    append_token: int

def filter_question(state: MyState) -> MyState:
    user_input = state["user_input"]
    session_id_table_answer = state["session_id_table_answer"]
    append_token = state["append_token"]
    api_key = settings.api_key
    version = settings.version
    
    question = settings.detect_data_related_question(user_input)
    response = llm_response(api_key, session_id_table_answer, version, 'normal', question)
    append_token = append_token + token_count(question) + token_count(response)
    state["question_type"] = response
    state["append_token"] = append_token
    return state

def filter_schema(state: MyState) -> tuple[MyState, str]:
    user_input = state["user_input"]
    table_name = state["table_name"]
    table_schema = state["table_schema"]
    raw_table_schema = state["raw_table_schema"]
    session_id_schema_query = state["session_id_schema_query"]
    question_type = state["question_type"]
    api_key = settings.api_key
    version = settings.version
    
    if '是'  in question_type:
        step_1_question = settings.prompt_schema(user_input, table_name, json_to_markdown(raw_table_schema))
        step1_response = llm_response(api_key, session_id_schema_query, version, 'normal', step_1_question)
        raw_table_schema = pd.DataFrame(raw_table_schema,columns=['COLUMN_NAME','COLUMN_COMMENT'])
        step1_response = fr'''首先

        {step1_response}'''
        state["raw_table_schema"] = fr'''{json_to_markdown(raw_table_schema)}'''
        state["table_schema"] = step1_response
    else:
        step1_response = ''

    return state,step1_response

def generate_sql(state: MyState) -> tuple[MyState, str]:
    user_input = state["user_input"]
    OWNER_SCHEMA = state["OWNER_SCHEMA"]
    table_name = state["table_name"]
    question_type = state["question_type"]
    table_schema = state["table_schema"]
    table_comment = state["table_comment"]
    session_id_table_query = state["session_id_table_query"]
    api_key = settings.api_key
    version = settings.version

    if '是' in question_type:

        step4_question = settings.prompt_SQL(user_input, table_name, table_schema,table_comment,OWNER_SCHEMA)
        step4_response = llm_response(api_key, session_id_table_query, version, 'normal', step4_question)
        step4_response_transform = oracle_query.extract_select_query(step4_response)
        
        if isinstance(step4_response_transform, str):
            if not safe_check_sql(step4_response_transform):
                print(f"Warning: Banned SQL operation detected: {step4_response_transform}")
        
        log_sql_operation(session_id_table_query, 'STEP1', 0, user_input, step4_response_transform)
        state["sql_query"] = step4_response_transform
    else:
        step4_response = ''

    return state,step4_response

def execute_sql(state: MyState) -> MyState:
    question_type = state["question_type"]

    if '是' in question_type:
        sql_query = state["sql_query"]
        query_result = sqlquery(sql_query)
        state["query_result"] = query_result
    else:
        query_result = ''
        state["query_result"] = query_result
    return state

def re_execute_sql(state: MyState) -> tuple[MyState, str]:
    sql_query = state["sql_query"]
    question_type = state["question_type"]
    user_input = state["user_input"]
    table_schema = state["table_schema"]
    query_result = state["query_result"]
    table_comment = state["table_comment"]
    session_id_table_query = state["session_id_table_query"]
    api_key = settings.api_key
    version = settings.version
    retry = 1
    max_retries = 2
    
    if '是' in question_type:
        while retry < max_retries:
            try:
                # 如果 query_result 是一個字串且長度小於 50，就計算裡面 "null" 出現的次數（存入 null_count）；否則設為 0
                null_count = pd.DataFrame(query_result).isnull().all(axis=1).iloc[0]
            except:
                null_count = 0
            try:
                # query_result 是字串，就計算 "SQLERROR" 的次數（存入 error_count）；否則設為 0。
                error_count = query_result.count("SQLERROR") if isinstance(query_result, str) else 0
            except:
                error_count = 0
            try:
                # query_result 等於字串 '[]'，則將 none_count 設為 1，否則為 0。
                none_count = (1 if query_result == '[]' else 0)
            except:
                none_count = 0
            
            #query_result 是空的（例如：None、空字串等）或是 query_result 是個列表，且列表中的任一記錄含有值為 None 的欄位
            #或是 null_count、error_count 或 none_count 其中任一值為 1
            if (not query_result or 
                (isinstance(query_result, list) and any(
                    isinstance(record, dict) and any(value is None for value in record.values()) 
                    for record in query_result)
                ) or null_count == 1 or error_count == 1 or none_count == 1):
                print(f"=== 重新生成 SQL，第 {retry} 次嘗試 ===")
                step4_question = settings.prompt_reSQL(user_input,sql_query, query_result, table_schema,table_comment)
                step4_response = llm_response(api_key, session_id_table_query, version, 'normal', step4_question)
                sql_query = oracle_query.extract_select_query(step4_response)
                
                if isinstance(sql_query, str):
                    if not safe_check_sql(sql_query):
                        print(f"Warning: Banned SQL operation detected: {sql_query}")
                
                log_sql_operation(session_id_table_query, 'STEP2', retry, user_input, sql_query)
                print(f"step4ai 第 {retry} 次重新輸出結果: {sql_query}")
                query_result = sqlquery(sql_query)
                state["sql_query"] = sql_query
                state["query_result"] = query_result
                retry += 1
                return state,step4_response
            else:
                break
    else:
        step4_response = '非數據問題'
        return state,step4_response
    
def analyze_result(state: MyState) -> tuple[MyState, int]:
    user_input = state["user_input"]
    sql_query = state["sql_query"]
    question_type = state["question_type"]
    table_schema = state["table_schema"]
    table_comment = state["table_comment"]
    raw_table_schema = state["raw_table_schema"]
    query_result = state["query_result"]
    session_id_table_answer = state["session_id_table_answer"]
    session_id_table_query = state["session_id_table_query"]
    DATAMARKET_NO = state["DATAMARKET_NO"]
    append_token = state["append_token"]
    api_key = settings.api_key
    version = settings.version
    

    if '是' in question_type:
        try:
            # 如果 query_result 是一個字串且長度小於 50，就計算裡面 "null" 出現的次數（存入 null_count）；否則設為 0
            null_count = pd.DataFrame(query_result).isnull().all(axis=1).iloc[0]
        except:
            null_count = 0
        try:
            # query_result 是字串，就計算 "SQLERROR" 的次數（存入 error_count）；否則設為 0。
            error_count = query_result.count("SQLERROR") if isinstance(query_result, str) else 0
        except:
            error_count = 0
        try:
            # query_result 等於字串 '[]'，則將 none_count 設為 1，否則為 0。
            none_count = (1 if query_result == '[]' else 0)
        except:
            none_count = 0
        
        if (not query_result or 
            (isinstance(query_result, list) and any(
                isinstance(record, dict) and any(value is None for value in record.values()) for record in query_result)
            ) or null_count == 1 or error_count == 1 or none_count == 1):
            status = 'fail'
            print("查詢結果無資料或包含錯誤")

            step6_question = settings.prompt_final_result_fail(dt.now().strftime("%Y-%m-%d %H:%M:%S"), sql_query, query_result, raw_table_schema)
        elif token_count(query_result) > 5000:
            status = 'success'
            print("查詢結果資料過多")
            step6_question = settings.prompt_final_result_limit(dt.now().strftime("%Y-%m-%d %H:%M:%S"), user_input, sql_query,table_schema)
            
        else:
            status = 'success'
            print("查詢結果成功")
            step6_question = settings.prompt_final_result_success(dt.now().strftime("%Y-%m-%d %H:%M:%S"), user_input, sql_query, query_result,table_schema,table_comment)
        
        step6_response = llm_response(api_key, session_id_table_answer, version, 'normal', step6_question)
        log_sql_operation(session_id_table_query, 'STEP3', 0, user_input, step6_response)
        print(f"step6ai 輸出結果: {step6_response}")
        
        result_message = fr'''編號:{DATAMARKET_NO}

    {step6_response}'''
        state["status"] = status
    else:
        step6_question = settings.prompt_not_data_related_question(user_input)
        result_message = llm_response(api_key, session_id_table_answer, version, 'normal', step6_question)

    state["append_token"] = append_token + token_count(step6_question) + token_count(result_message)
    state["final_message"] = result_message
    print('已累積:',state["append_token"])
    return state,state["append_token"]

