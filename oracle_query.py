
import pandas as pd
import cx_Oracle
import re
import configparser
import settings

def extract_select_query(query):
    #query = query.replace('```sql','').replace('```','').replace(';','')
    match = re.search(r"SELECT\s+(.*)\s+ONLY", query, re.IGNORECASE | re.DOTALL)
    match_0 = re.search(r"```sql\s+(.*)\s+```", query, re.IGNORECASE | re.DOTALL)
    match_1 = re.search(r"WITH\s+(.*)\s+ONLY", query, re.IGNORECASE | re.DOTALL)
    if match_1:
        return fr'''WITH {match_1.group(1).strip()} ONLY'''
    elif match:
        return fr'''SELECT {match.group(1).strip()} ONLY'''
    elif match_0:
        return (match_0.group(1).strip()).replace(';','')
    elif query[0] == ' ':
        return query.replace('\n', '', 1).replace(' ', '', 1)
    else:
        return query

def output_type_handler(cursor, name, default_type, size, precision, scale):
    if default_type == cx_Oracle.DB_TYPE_CLOB:
        return cursor.var(
            cx_Oracle.DB_TYPE_VARCHAR,
            size=4000,  # 根據預期字串長度調整
            arraysize=cursor.arraysize,
            outconverter=lambda value: value.read() if (value is not None and hasattr(value, 'read')) else value
        )

def sql_query(query):
    """
    執行 SQL 查詢：
      - 若為 SELECT 或 WITH 查詢，回傳 JSON 格式的結果
      - 否則直接執行並 commit
    """
    # 移除註解，保持 SQL 語句乾淨
    query_no_comments = re.sub(r'^\s*--.*$', '', query, flags=re.MULTILINE).strip()
    query_cleaned = query_no_comments  # 若有進一步處理需求，可在此調整

    # 建立連線參數（此處使用 encrypt_decrypt 解密連線資訊）
    h = settings.host
    p = settings.port
    s = settings.service_name
    d = cx_Oracle.makedsn(h, p, s)
    connection = cx_Oracle.connect(
        settings.username,
        settings.password,
        d
    )
    cursor = connection.cursor()
    # 設定 output type handler，自動處理 CLOB 欄位
    cursor.outputtypehandler = output_type_handler

    try:
        # 若為查詢語句，執行並轉成 JSON 回傳
        if query_cleaned.lower().startswith('select') or query_cleaned.lower().startswith('with'):
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            df = pd.DataFrame(data, columns=columns)
            return df.to_json(orient='records')
        else:
            # 非查詢語句則執行並 commit
            cursor.execute(query)
            connection.commit()
            return None
    except Exception as e:
        print(f"SQLERROR: {e}")
        return f"SQLERROR: {e}"
    finally:
        cursor.close()
        connection.close()