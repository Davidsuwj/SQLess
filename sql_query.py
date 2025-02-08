try:
    import cx_Oracle
except:
    pass
import time
import os
import re
import pandas as pd
import pandasql as ps
import settings

def extract_select_query(query):
    query = query.replace('sql','').replace('','').replace(';','')
    match = re.search(r"SELECT\s+(.*?)\s+ONLY", query, re.IGNORECASE | re.DOTALL)
    if match:
        return fr'''SELECT {match.group(1).strip()} ONLY'''
    elif query[0] == ' ':
        return query.replace('\n', '', 1).replace(' ', '', 1)
    else:
        return query
    

def sql_query(db_type,query):

    if db_type == 'Oracle SQL':
        try:
            dsn = cx_Oracle.makedsn(settings.host, settings.port, settings.service_name) 
            connection = cx_Oracle.connect(settings.username, settings.password, dsn)

            cursor = connection.cursor()
        except:
            pass
        try:
            if query.lower().startswith('select') or query.lower().startswith('with'):
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]  
                data = cursor.fetchall()
                if pd.DataFrame(data, columns=columns).empty:
                    return pd.DataFrame(data, columns=columns)
                else:
                    df = pd.DataFrame(data, columns=columns).to_json(orient='records')
                cursor.close()
                connection.close()
                return df
            else:
                cursor.execute(query)
                connection.commit()
                cursor.close()
                connection.close()
                return None
        except Exception as e:
                print(fr"SQLERROR:{e}")
                cursor.close()
                connection.close()