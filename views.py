import pandas as pd
from flask import Flask, request, jsonify
from datetime import datetime as dt
import json
import sql_query 
import LLM_response as llm
import settings
import re

#取得使用者輸入的table_name
def table_sort(api_key=None, session=None, user_input=None):
    # 儲存結果變數
    result = ''
    try:
        # 如果有提供 api_key，處理歷史訊息
        if api_key:
            df = pd.DataFrame(llm.get_history(api_key, session))
            df = df[df['role'] == 'user']  # 過濾用戶訊息
            content = df['content'].iloc[-1].split('\n', 1)[0]
        # 如果沒有 api_key，使用 user_input
        elif user_input:
            content = user_input
        else:
            raise ValueError("必須提供 api_key 或 user_input")

        #提取DS&DL字串
        match = re.search(r'(DL|DS)(.{5})', content.upper())
        if match:
            result = match.group(1) + re.sub(r'[^A-Za-z0-9]', '', match.group(2))
    except Exception as e:
        print(f"發生錯誤: {e}")

    return result

#將result轉換成DataFrame
def result_to_df(result):
    try:
        rows = []
        for item in result:
            row_data = item.copy()
            rows.append(row_data)
        
        df = pd.DataFrame(rows)
    except:
        df = json.loads(result)
    return df

def execute(user_input,table_name,table_schema,session_id_table_query,session_id_table_answer):

    api_key = settings.API_KEY
    version = settings.version
    db_type = settings.db_type

    #step4:根據使用者問題來生成出符合使用者問題的oracle SQL查詢語句並且參考step3的欄位資訊
    step4_question = fr'''

    使用者問題如下：
    {user_input}

    請注意：

    1. 我們已找到對應的表名為 {table_name}，其 schema 資訊為：

    {table_schema}

    2. 請根據以上欄位資訊，生成符合使用者問題的 {db_type} 查詢語句。

    3.若有地名相關的文字，請自動轉為英文，條件請嘗試用 in (簡寫，全寫)。

    4.若有客戶名，請自行判斷是否需轉為英文，條件請嘗試用 LIKE %做查詢。

    5.看到 & 一律使用 in (條件,條件)。

    6.所有條件請用TRIM(UPPER(REPLACE(欄位,' ',''))) = TRIM(UPPER(REPLACE(INPUT,' ','')))。

    7.因為輸出的SQL執行完後要再味回給CHATGPT，所以盡量幫我多用聚合函數，讓資料量體不要那麼大，最後要FETCH FIRST 1000 ROWS ONLY;。

    請嚴格遵守以下格式回覆(輸出不要換行)，<<<<<重要!!!!!一次只能產出一句SQL，並且一定要符合user給的條件>>>>>：

    SELECT 欄位 FROM {table_name} WHERE UPPER(條件) = UPPER() ORDER BY 欄位 ASC'''


    step4_response = llm.chat_response(api_key,session_id_table_query,version,'normal',step4_question)
    #清理step4_response sql query以外的文字
    step4_response_transform = sql_query.extract_select_query(step4_response)
    
    #其他dml,ddl卡控機制
    try:
        if "delete" in step4_response_transform.lower() if isinstance(step4_response_transform, str) else False == True:
            return {
                'message': 'Error in searching data, status: Delete banned.',
                'sql_query': step4_response_transform
            }
        if "insert" in step4_response_transform.lower() if isinstance(step4_response_transform, str) else False == True:
            return {
                'message': 'Error in searching data, status: Insert banned.',
                'sql_query': step4_response_transform
            }
    except:
        pass

    print(fr'''step4ai輸出結果: {step4_response_transform}''')

    #step5:根據step4輸出的oracle SQL查詢語句來查詢資料，如果第一次查詢沒有資料，則重新查詢
    step5_table_find = sql_query.sql_query(db_type,fr'''{step4_response_transform}''')

    retry = 1
    while retry < 2:

        try:
            null_count = step5_table_find.count("null")
        except:
            null_count = 0

        if (step5_table_find is None or len(step5_table_find) == 0 or any(isinstance(record, dict) and any(value is None for value in record.values()) for record in step5_table_find)) or null_count == 1:
      
            print(fr'''========================================重新生成: {retry}次===========================================''')
            step4_question = fr'''
            上一版生成的 SQL 無效，輸出的 output 為 none 或 null，但結果不應該沒有資料。

            上一版生成的 SQL 為：
            {step4_response_transform}

            再給你參考一次table schema:
            {table_schema}

            請特別注意以下幾點，如果沒有特別注意的話我會被你害慘了：
            1.嘗試在 SELECT、WHERE、ORDER BY 各個部分中，使用相似的欄位進行篩選或計算，請仔細檢查sql函數是否符合oracle sql的規範。

            2.請根據以上欄位資訊，生成符合使用者問題的 Oracle SQL 查詢語句。

            3.若有地名相關的文字，請自動轉為英文，條件請嘗試用 in (簡寫，全寫)。

            4.若有客戶名，請自行判斷是否需轉為英文，條件請嘗試用 LIKE %做查詢。

            5.看到 & 一律使用 in (條件,條件)。

            6.所有條件請用TRIM(UPPER(REPLACE(欄位,' ',''))) = TRIM(UPPER(REPLACE(INPUT,' ','')))。

            7.因為輸出的SQL執行完後要再味回給CHATGPT，所以盡量幫我多用聚合函數，讓資料量體不要那麼大，最後要FETCH FIRST 1000 ROWS ONLY;。

            8. 確保生成的 SQL 語句格式如下，並嚴格按照要求回覆(輸出不要換行)，一次只能產出一句SQL：

            SELECT 欄位 FROM {table_name}  WHERE 條件  ORDER BY 欄位 ASC FETCH FIRST 1000 ROWS ONLY; '''

            step4_response = llm.chat_response(api_key,session_id_table_query,version,'normal',step4_question)
            step4_response_transform = sql_query.extract_select_query(step4_response)

            #其他dml,ddl卡控機制
            try:
                if "delete" in step4_response_transform.lower() if isinstance(step4_response_transform, str) else False == True:
                    return {
                        'message': 'Error in searching data, status: Delete banned.',
                        'sql_query': step4_response_transform
                    }
                if "insert" in step4_response_transform.lower() if isinstance(step4_response_transform, str) else False == True:
                    return {
                        'message': 'Error in searching data, status: Insert banned.',
                        'sql_query': step4_response_transform
                    }
            except:
                pass

            print(fr'''step4ai第{retry}次重新輸出結果: {step4_response_transform}''')
            step5_table_find = sql_query.sql_query(db_type,fr'''{step4_response_transform}''') 
        else:
            break
        retry += 1

    #step6:根據step5輸出的資料來回答使用者的問題

    try:
        null_count = step5_table_find.count("null")
    except:
        null_count = 0

    if (step5_table_find is None or len(step5_table_find) == 0 or any(isinstance(record, dict) and any(value is None for value in record.values()) for record in step5_table_find)) or null_count == 1:
        print('sql query失敗')
        step6_question = fr'''

        請根據
        
        輸出的sql = 
        {step4_response_transform}

        table schema = 
        {table_schema}

        -首先跟USER說無查到相關資料 QAQ
        
        1.回覆給USER 參考:**輸出的sql** 給的條件以及**SQL欄位名稱**(不用回覆用到的函數)，並詢問條件及欄位名稱是否正確。(不要參考table schema)

        2.欄位的部分:參考輸出sql where後面的**所有**欄位 & 參考 table schema相近的欄位名稱，給USER你覺得可能與之相似的column name 有哪些? 每個欄位最少列2個以上。

        3.USER要求的條件值: 參考輸出sql where的條件**值**，給USER你覺得可能與之相同的值有哪些? ex. TAIWAN = TW, US = USA, AMERICA, APPLE = APPL, NVDA = NVDIA。

        4.SELECT 後面計算用到的**原始**欄位名稱(不用回覆用到的函數以及 as 後面的欄位名稱)

        5.回復的時候不要有**SQL**這三個相關的字，也不用回復FETCH的條件


    '''

    else:

        step6_question = fr'''
        請根據下列資訊，使用專業且詳盡的語氣，直接回答使用者的問題。請注意：

        1.嚴禁在回答中出現任何程式碼或與程式實作相關的描述。

        2.回答內容必須簡潔明瞭，同時具備充分的分析深度，確保直接解決使用者所提出的問題。

        使用者問題：
        {user_input}

        輸出的sql:
        {step4_response_transform}

        已找到的相關資訊：
        {step5_table_find}


        1.請以專業人士的態度，根據以上資訊進行分析，並提供數據給user & 一個詳細解析本份數據的回答，
        一樣要給 user:
            1.1 - [SQL where 後面給的所有 **條件值** 以及 **下條件的欄位名稱**(不用回覆用到的函數)] 。
            1.2 - 計算用到的**原始**欄位名稱(不用回覆用到的函數以及 as 後面的欄位名稱)。
        
        2.回復的時候不要有**SQL**這三個相關的字，也不用回復FETCH的條件

        '''

    step6_response = llm.chat_response(api_key,session_id_table_answer,version,'normal',step6_question)

    print(fr'''step6ai輸出結果: {step6_response}''')
    result = fr'''Table:{table_name}
{step6_response}'''

    return {
        'message': result.replace('*',''),
        'sql_query': step4_response_transform
    }

def generate_charts(session_id_table_chart, step4_response_transform,user_input):
    api_key = settings.API_KEY
    version = settings.version

    # 取得查詢結果
    table_find = sql_query.sql_query(settings.db_type,fr'''{step4_response_transform}''')
    print('圖表繪製:',user_input)
    # 建立 prompt，要求 AI 生成繪圖代碼
    # 請務必在範本裡面，讓 AI 在程式最後 result = img_base64
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
    output = llm.chat_response(api_key, session_id_table_chart, version,'normal', question)
    output = output.replace('python', '').replace('', '')

    print("=== AI 產生的程式碼 ===\n", output)

    try:
        # 執行 AI 生成的程式碼
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

def get_tables():
    table = sql_query.sql_query(settings.db_type,''' ''')
    data = json.loads(table)
    df = pd.DataFrame(data)
    return  df['table_name'].to_list()

def get_table_schema(table_id: str) -> tuple[str, str]:
    """快速獲取表格結構"""
    try:
        # 查詢表名
        table_name_query = f"""  """
        table_result = sql_query.sql_query(settings.db_type,table_name_query)
        
        table_result = json.loads(table_result)
        # 獲取表名    
        table_name = pd.DataFrame(table_result)['table_name'].iloc[0]
        
        # 查詢結構
        schema_query = f""" """
        schema_result = sql_query.sql_query(settings.db_type,schema_query)
        schema_result = json.loads(schema_result)
        schema_df = pd.DataFrame(schema_result)
        schema = schema_df.to_dict(orient='records')
        
        return schema, table_name
        
    except Exception as e:
        return None, None