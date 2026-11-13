import csv

import pandas as pd
# from bs4 import BeautifulSoup

df = pd.read_csv(
    'resume_data.csv',
    sep=',',                 # 分隔符，TSV用 '\t'
    encoding='utf-8',        # 编码，中文乱码常用 'gbk' / 'gb2312' / 'utf-8-sig'
    header=0,                # 第几行为列名，None表示无表头
)

id = 0
pre = ""
for val in df["Category"]:
    if val != pre:
        pre = val
        print(val)
    # with open("./tag.csv", 'a') as f:
    #     f.write("{}, {}\n".format(id, val))
    #     id += 1
    # with open("./resume_html/resume{}.html".format(id), "w") as f:
    #     f.write(val)
    #     print("resume{} has been readed".format(id))
    # id += 1

# id = 0
# with open("resume{}.html".format(id), "r") as f:
#     # html = f.read()
#     # soup = BeautifulSoup(html, "lxml")



