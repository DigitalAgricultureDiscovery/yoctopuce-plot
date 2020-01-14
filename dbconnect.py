import MySQLdb

def connection():
    conn = MySQLdb.connect(host="localhost", 
                           user = "root",
                           passwd = "waterquality",
                           db = "pythonprogramming")
    c =conn.cursor()

    return c, conn
