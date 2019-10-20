import os
import sys
import json
import re
import pandas as pd
import random
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
import numpy as np


def data_clean(self, text='【本报讯】，2018年4月10日这位副厅长每年每次  受贿30万\n后都--__打借条，担任嘉陵区委书记的3.3年间，？；？，，收受67%人民币……,▶全南'):
    text = re.sub(r"\s+", "", text)
    text = text.replace('！', '!')
    text = text.replace('？', '?')
    text = text.replace('，', ',')
    pattern = "[\u4e00-\u9fa5]+|[,。?!]+"  # 中文正则表达式
    regex = re.compile(pattern)  # 生成正则对象
    results = regex.findall(text)
    text = ''.join(results)
    # 删除常见计量单位
    text = re.sub(r'[年月日个十百千万亿]+', '', text)
    # 删除无意义的单词
    stopwords = ['查看更多', '返回搜狐', '责任编辑', '本报讯', '来自客户端', '复制到浏览器打开']
    for each in stopwords:
        text = re.sub(each, '', text)
    if not text: text = '无'
    return text


def read_data(input_file,data_process_output):
    df = pd.read_csv(input_file, sep='\t')
    print('行列数', df.shape)
    # 删除空行
    df.dropna(how='any', inplace=True)
    print('行列数', df.shape)
    # print(df.head())
    # print(df['question'].head())
    # print(df['answer'].head())
    # 按照句长筛选
    new_df = df[(df['question'].str.len() >= 64) & (df['question'].str.len() <= 256)& (df['answer'].str.len()>= 64) & (df['answer'].str.len() <= 256)]
    print('行列数', new_df.shape)
    torned_df = df[~df.index.isin(new_df.index)]
    torned_answer = torned_df['answer'].tolist()

    question,answer,label = [],[],[]
    count = 0
    for index, row in new_df.iterrows():
        # 正样例
        question.append(row[0])
        answer.append(row[1])
        label.append('1')

        # 负样例
        question.append(row[0])
        label.append('0')
        # 负样本答案
        neg_answer = random.sample(torned_answer, 1)
        answer.append(neg_answer)

    assert len(question) == len(answer) == len(label)

    data = pd.DataFrame({
        'id': [x for x in range(len(question))],
        'title': question,
        'content': answer,
        'label': label})

    train_data = data.sample(frac=0.8, random_state=0, axis=0)
    test_data = data[~data.index.isin(train_data.index)]
    print('traindata:',train_data.shape)
    print('testdata:',test_data.shape)

    if not os.path.exists(data_process_output): os.makedirs(data_process_output)
    train_data.to_csv(os.path.join(data_process_output, "train.csv"), index=False, header=False)
    test_data.to_csv(os.path.join(data_process_output, "test.csv"), index=False, header=False)


if __name__ == "__main__":
    read_data('../DATA/CQA/QAPro.txt','/home/lsy2018/文本匹配/DATA/CQA/data_1020/')