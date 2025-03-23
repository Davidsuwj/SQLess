import random
from datetime  import datetime
import tiktoken

def token_count(text):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    return len(tokens)



ai_version = 'azure'
api_key = ''
version = 'gpt-4o'
service = 'azure' 
api_version = ''
endpoint = ''


# open ai token 計算模組
model = "gpt-4o"

# 資料庫連線資訊
host = ''
port = ''
service_name = ''
username = ''
password = ''






emo_list = ['你是是專業的數據分析師']

# 判斷是否要查資料
def detect_data_related_question(user_input):
    output = fr'''
你是一個專業的 AI 助理，負責判斷使用者的問題是否與數據查詢相關。

### 📌 判斷標準：
- **數據相關問題** 通常包含：
  - 需要查詢、篩選、計算或統計的內容
  - 可能涉及時間、數量、金額、趨勢、變化、排名等
  - 可能提及特定的條件，例如某個區域的銷量、某段時間內的變化等

- **非數據問題** 可能是：
  - 詢問概念、背景知識或一般討論
  - 詢問規則、政策或業務邏輯，而不是具體的數據查詢
  - 需要一般性的建議或決策建議，而非具體數據

請判斷以下問題是否與數據查詢相關，並回覆 **「是」或「否」**：
---
使用者問題：
"{user_input}"
---
請僅回覆 **「是」或「否」**，不得提供額外說明。
'''
    print('第0槍schema篩選:',token_count(output))
    return output

#schema篩選相關的prompt
def prompt_schema(user_input, table_name, table_schema):

    output = fr'''
你是資深數據工程師。根據使用者輸入，精準篩選SQL可能用到的Schema欄位：

【使用者問題】：
{user_input}

【資料表名稱】：
{table_name}

【Schema欄位】：
{table_schema}

【任務要求】：
- 根據以上資訊，判斷此次問題是否連貫，並列出可能被使用到的欄位。
- 若有名稱相似或語意接近的欄位，全部列出，不可合併或省略。

- 最後以 **markdown格式呈現**，僅包含以下欄位：
  column_name, 格式, COLUMN_COMMENT(完整內容), COLUMN_LOGIC(完整內容)

【注意事項】：
- 只輸出表格內容，不允許其他文字說明或廢話。
- 務必保留COLUMN_COMMENT與COLUMN_LOGIC完整原文，不可省略。
- 禁止花費過多時間思考，立即回覆。
'''

    print('第一槍schema篩選:',token_count(output))
    return output

#第一次TEXTTOSQL轉換
def prompt_SQL(user_input,table_name,table_schema,table_comment,OWNER_SCHEMA):
    output = fr'''
你是專業的數據工程師，使用者問題如下:

{user_input}

當前日期:{datetime.now().strftime('%Y-%m-%d')}

請參考以下table_comment資訊:
{table_comment}

請注意：
2. 已找到表名為 `{table_name}`，其 schema 資訊(**請用markdown格式解讀**)：
{table_schema}

3. 請參考以上schema資訊(**若COLUMN_LOGIC有值請**參考不要照抄**該欄位條件，不然我會被開除**)並根據 使用者問題，篩選**必要**的欄位，生成符合要求且正確的 Oracle SQL 查詢語句。
4. 地名自動轉英文，條件盡量使用 in (簡寫，全寫)。
5. 客戶名則判斷是否需轉英文，條件盡量使用 LIKE %。
6. 看到 & 請使用 in (條件,條件)。
7. 條件格式：TRIM(UPPER(REPLACE(欄位,' ',''))) = TRIM(UPPER(REPLACE(INPUT,' ',''))) ，如果使用者問題沒有明確跟你說條件，請勿自行下條件。
8. 其他條件:請盡量使用聚合函數來壓縮資料量體，並且欄位做聚合後請重新命名。
   
9. 根據要求 & COLUMN_LOGIC 請輸出一句 簡單且正確的SQL，請給予最低限度的數據量，也可以用with，格式必須符合：
SELECT 欄位 FROM {OWNER_SCHEMA}.{table_name} WHERE TRIM(UPPER(REPLACE(欄位,' ',''))) = TRIM(UPPER(REPLACE(INPUT,' ',''))) ORDER BY 欄位 ASC
並在結尾**務必附上** :   FETCH FIRST **根據需求而定數量(預設最多1000000)** ROWS ONLY;

10.禁止使用EXTRACT(quarter FROM )
11.在SQL內任何條件計算請計算完後再進行篩選。


ps.如果找不到 使用者問題 所提到的條件欄位，請回覆無法找到相關資料。
'''
    print('第二槍sql產生篩選:',token_count(output))
    return output

#執行失敗後，第二次TEXTTOSQL轉換
def prompt_reSQL(user_input,sql_query,query_result,table_schema,table_comment):
    output = fr'''
上一版 SQL 輸出如下：
{sql_query}
但查詢結果為：
{query_result}
請參考以下 table schema (**請用markdown格式解讀**)：
{table_schema}

請參考以下table_comment資訊:
{table_comment}

當前日期:{datetime.now().strftime('%Y-%m-%d')}

你是專業的數據工程師，請再次根據{user_input}要求生成符合條件的 Oracle SQL 查詢語句(**若COLUMN_LOGIC有值請特別**參考不要照抄**該欄位條件**)：

- 確認 WHERE 條件符合 Oracle SQL 規範

- 若有地名，轉英文使用 in (簡寫，全寫)

- 若有客戶名，判斷是否轉英文並使用 LIKE %查詢

- 條件格式：TRIM(UPPER(REPLACE(欄位,' ',''))) = TRIM(UPPER(REPLACE(INPUT,' ',''))) or TRIM(UPPER(REPLACE(欄位,' ',''))) like TRIM(UPPER(REPLACE(%INPUT%,' ','')))

- 其他條件:*****請務必使用聚合函數來壓縮資料量體*****並且欄位做聚合後請重新命名，另外根據要求，請給予最低限度的數據量，。

- 請輸出一句查詢語句，結尾**務必附上** :  FETCH FIRST **根據需求而定數量(預設最多1000000)** ROWS ONLY;

- 禁止使用EXTRACT(quarter FROM )

- 在SQL內任何條件計算請計算完後再進行篩選。

ps.如果找不到 使用者問題 所提到的條件欄位，請回覆無法找到相關資料。

'''
    print('第三槍sql產生篩選:',token_count(output))
    return output

#查詢結果總結
def prompt_final_result_fail(time, sql_query, query_result, table_schema):
    random_choice = random.choice(emo_list)
    output = fr'''
            當前日期:{time}
            請根據

            輸出的sql = 
            {sql_query}

            結果:
            {query_result}

            table schema = 
            {table_schema}

            -查無資料
            -**{random_choice}跟USER說沒有找到資料(這部分你自己發揮看要怎麼講user才會買單)**

            -目前的篩選
            (只回覆一次，**不要提到你我他**) where篩選的欄位**(不用回覆用到的函數 & where)** =  **輸出的sql** 給的條件(有計算的話給我計算完的值，日期給我實際的數字，其餘給我一般值，沒有則顯示無)，並詢問條件及欄位名稱是否正確。 
            ** 請讀取dataframe格式並用**表格呈現** >>{{輸出的欄位名稱: [**欄位名稱(英文) 加上(COLUMN_COMMENT)**], 條件值:[值] }}

            -相似欄位
            (只回覆一次，**不要提到你我他**):參考**輸出sql where & select後面的**所有**欄位 & 參考 **所有table schema相似的欄位名稱**或如果有USER給的欄位是SCHEMA都沒有查到的，請告知，並給USER你覺得可能與之相似的所有column name 有哪些? \
            ** 請讀取dataframe格式並用**表格呈現** >>{{輸出的欄位名稱: [**欄位名稱(英文) 加上(COLUMN_COMMENT)**], 相似的欄位: [**所有相似的欄位 加上(COLUMN_COMMENT)**] }} 每個欄位請換行**

            -相似條件值
            (只回覆一次，**不要提到你我他**): 參考輸出sql where的條件**值**，給USER你覺得可能與之相同的值有哪些? ex. TAIWAN = TW, US = USA, AMERICA, APPLE = APPL, NVDA = NVDIA
             **用表格彙整>> 輸出的條件值,可能的條件值。**

            -回復的時候不要有**SQL**這三個相關的字，也不用回復FETCH的條件
        '''
    print('第四槍失敗:',token_count(output))
    return output

#成功但資料量過大
def prompt_final_result_limit(time,user_input,sql_query,table_schema):
    random_choice = random.choice(emo_list)
    output = fr'''
            當前日期:{time}
            請根據下列資訊，使用{random_choice}，直接回答使用者的問題。請注意：

            嚴禁在回答中出現任何程式碼或與程式實作相關的描述。

            使用者問題：
            {user_input}

            輸出的sql:
            {sql_query}
           
            schema:
            {table_schema}


            開頭:很抱歉，因為資料量龐大，無法一次性呈現所有資料，請點選對話框下載按鈕~
            
            一樣要給 user:
                -回覆給USER 參考(只回覆一次，**不要提到你我他**): *where*  篩選的欄位**(不用回覆用到的函數 & "WHERE"這個字 & GROUP BY, ORDER BY 的欄位  & SELECT 的欄位)** =  **輸出的sql** 給的條件(有計算的話給我計算完的值，其餘給我一般值，沒有則不要顯示)。 
                 用**表格呈現以下內容** >>
                 |篩選的欄位| 條件值|
                 |---|---|
                 |**according to schema, present with **column_name** and (column comment) else you'll be fired** | **輸出的sql** 給的條件不用回覆用到的函數 |

                -(只回覆一次，**不要提到你我他以及SELECT這個字**) *SELECT* 後面用到的**原始**欄位名稱 (不用回覆用到的函數以及 as 後面的欄位名稱)
                 用**表格呈現以下內容** >>
                 |用到的原始的欄位|
                 |---|
                 |**according to schema, present with **column_name** and (column comment) else you'll be fired**|
            
            -回復的時候不要有**SQL**這三個相關的字，也不用回復FETCH的條件

            '''
    print('第四槍成功過大:',token_count(output))
    return output

#成功
def prompt_final_result_success(time,user_input,sql_query,query_result,table_schema,table_comment):
    random_choice = random.choice(emo_list)
    output = fr'''

            相關結果如下:

            {query_result}

            使用者問題：
            {user_input}

            輸出的sql:
            {sql_query}

            schema:
            {table_schema}

            其他注意事項:
            {table_comment}

            當前日期:{time}

            版面配置:
            由上而下:   原始數據呈現 >> 相關條件資訊

            
            ps.**{random_choice}，簡單又簡短的分析一下內容**：
            原始數據呈現:
            (不管字串長或短都以表格呈現，並且要有表頭，表頭請白話翻譯)
            
            相關條件資訊:
                -回覆給USER 參考(只回覆一次，**不要提到你我他**): *where*  篩選的欄位**(不用回覆用到的函數 &  "WHERE"這個字  & GROUP BY, ORDER BY 的欄位  & SELECT 的欄位)** =  **輸出的sql** 給的條件(有計算的話給我計算完的值，其餘給我一般值，沒有則不要顯示)。 
                 用**表格呈現以下內容** >>
                 |篩選的欄位| 條件值|
                 |---|---|
                 |**according to schema, present with **column_name** and (column comment) else you'll be fired** | **輸出的sql** 給的條件不用回覆用到的函數 |

                -(只回覆一次，**不要提到你我他以及SELECT這個字**)*SELECT* 後面用到的**原始**欄位名稱 (不用回覆用到的函數以及 as 後面的欄位名稱)
                 用**表格呈現以下內容** >>
                 |用到的原始的欄位|
                 |---|
                 |**according to schema, present with **column_name** and (column comment) else you'll be fired**|
                 
            回復的時候不要有**SQL**這三個相關的字，不用回復FETCH的條件，也不用回復**COLUMN_COMMENT這個字**
            '''

    print('第四槍成功:',token_count(output))
    return output

#非數據問題
def prompt_not_data_related_question(user_input):
    return fr'''請根據{user_input}的問題，回答他的疑問。'''
