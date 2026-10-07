# --------------------------------------------------
# MySQL 연결 테스트
#
# 목적:
# Python에서 MySQL의 mbc_kpop_data 데이터베이스에
# 정상적으로 접속할 수 있는지 확인한다.
# --------------------------------------------------

import os

# MySQL 연결을 위한 라이브러리
import mysql.connector

# .env 파일의 환경변수를 읽기 위한 라이브러리
from dotenv import load_dotenv


# --------------------------------------------------
# 1. .env 파일 읽기
# --------------------------------------------------

load_dotenv()

# .env에 저장한 MySQL 접속 정보를 가져온다.
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")


# --------------------------------------------------
# 2. MySQL 연결
# --------------------------------------------------

connection = mysql.connector.connect(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE
)


# --------------------------------------------------
# 3. 연결 성공 여부 확인
# --------------------------------------------------

if connection.is_connected():
    print("✅ MySQL 연결 성공")
    print("Database:", MYSQL_DATABASE)


# --------------------------------------------------
# 4. 연결 종료
#
# DB 작업이 끝나면 연결을 닫아준다.
# --------------------------------------------------

connection.close()

print("✅ MySQL 연결 종료")