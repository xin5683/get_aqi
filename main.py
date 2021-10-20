import json

import requests
from loguru import logger
import time
import re
import execjs
import base64
import os
import pandas as pd
from urllib.parse import urljoin
import urllib.parse
import random


# 随机延时 0~y 秒
def delay_0_y_s(random_delay_num):
    y = float(random_delay_num)
    time.sleep(random.random() * y)


sess = requests.Session()
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36 Edg/94.0.992.50',
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.aqistudy.cn"
}


def getJS():
    # 请求首页,
    r = sess.get('https://www.aqistudy.cn/historydata/daydata.php?city=%E6%9D%AD%E5%B7%9E&month=202110',
                 headers=HEADERS)
    logger.info(f'首页的状态码：{r.status_code}')
    text = r.text
    # 获取首页加载js的名字
    url = re.findall('<script type="text/javascript" src="(.*?)"></script>', text)[1]
    t = int(time.time())
    params = (
        ('v', str(t)),
    )
    # 请求获取js代码
    response = sess.get(f'https://www.aqistudy.cn/historydata/{url}', headers=HEADERS,
                        params=params)
    logger.info(f"请求js的状态码：{response.status_code}")
    eval_text = re.search(r'eval\((.*)\)', response.text).group(1)  # 返回一段js函数，去掉eval
    eval_text = execjs.eval(eval_text)  # 执行js获得base64加密后的js
    num = eval_text.count('dweklxde')  # 计算进行了几次base64，有0,1,2，三种情况
    logger.info('num={}'.format(num))
    if num != 0:  # 如果有进行base64加密
        eval_text = re.search(r"'(.*?)'", eval_text).group(1)  # 取出base64加密后的代码解密
        for i in range(num):
            eval_text = base64.b64decode(eval_text.encode()).decode()
        enc_func_name = re.search('if \(!(.*?)\)(.*?){(.*?)var (.*?)=(.*?)\((.*?)ajax', eval_text, re.S).group(
            5).strip()  # 获取加密函数的函数名
        dec_func_name = re.search('success: function \((.*?)\)(.*?)= (.*?)\(', eval_text, re.S).group(3)  # 解密函数的函数名
        data_name = re.search('data: {(.*?):(.*?)}', eval_text).group(1).strip()  # post请求时请求的参数名
    else:  # 生成的js没有加密
        enc_func_name = re.search('if\(!(.*?)\)\{var (.*?)=(.*?)\((.*?)ajax', eval_text).group(3).strip()
        dec_func_name = func_name = re.search('success:function\((.*?)\)(.*?)=(.*?)\(', eval_text).group(3)
        data_name = re.search('data:{(.*?):(.*?)}', eval_text).group(1).strip()
    logger.info("data_name={}".format(data_name))
    logger.info("enc_func_name={}".format(enc_func_name))
    logger.info("dec_func_name={}".format(dec_func_name))
    # logger.info("eval_text={}".format(eval_text))
    return data_name, enc_func_name, dec_func_name, eval_text


def getParames(func_name, text, query):
    # 根据解密出来的js与扣出来的静态js拼接执行
    node = execjs.get()
    with open('./1.js', 'r', encoding='utf-8') as f:
        buf = f.read() + text
        with open('tmp.js', 'w', encoding='utf-8') as jsf:
            jsf.write(buf)
        ctx = node.compile(buf)
        # print('call=', func_name, query);
        sign = ctx.call(func_name, 'GETDAYDATA', query)
        # logger.info(sign)
        return sign, ctx


def decrypt(data, dec_func_name, ctx):
    # 解密请求的数据
    data = ctx.call(dec_func_name, data)
    logger.info(data)
    return data


def getEncryptData(data_name, sign):
    # 请求api获取加密的数据
    data = {}
    data[data_name] = sign
    response = sess.post('https://www.aqistudy.cn/historydata/api/historyapi.php', headers=HEADERS, data=data)
    logger.info(f"请求数据的状态码：{response.status_code}")
    # logger.info(response.text)
    return response.text, response.status_code


def get_year_months(start_year, start_month, end_year, end_month):
    start_year, start_month, end_year, end_month = [int(i) for i in [start_year, start_month, end_year, end_month]]
    year_months = []
    if start_year < end_year:
        for year in range(start_year, end_year + 1):
            if year == start_year:
                if start_month > 12 or start_month < 1:
                    raise ValueError
                else:
                    for month in range(start_month, 13):
                        year_months.append(year * 100 + month)
            elif year == end_year:
                if end_month > 12 or end_month < 1:
                    raise ValueError
                else:
                    for month in range(1, end_month + 1):
                        year_months.append(year * 100 + month)
            else:
                for month in range(1, 13):
                    year_months.append(year * 100 + month)
    elif start_year == end_year:
        if start_month <= end_month:
            for month in range(start_month, end_month + 1):
                year_months.append(start_year * 100 + month)

    return year_months


if __name__ == '__main__':

    city_set = ['郑州', '开封', '洛阳', '平顶山', '安阳', '鹤壁', '新乡', '焦作', '濮阳', '许昌', '漯河', '三门峡', '南阳', '商丘', '周口', '驻马店', '济源']
    year_months = get_year_months(2014, 1, 2021, 10)  # 包括最后年的最后月

    os.environ["EXECJS_RUNTIME"] = 'Node'
    if execjs.get().name != 'Node.js (V8)':
        logger.error('未能获取到node js')
        exit(-1)
    logger.info(execjs.get().name)

    rps_code = 0
    data_name = None
    enc_func_name = None
    dec_func_name = None
    text = None
    dataFrame = None

    for k in range(0, len(city_set)):
        city_chinese_name = city_set[k]
        # 将城市中文名进行URL编码
        city_name = urllib.parse.quote(city_chinese_name)
        # print(city_name)
        city_name = urllib.parse.unquote(city_name)
        # print(city_name)

        dataFrame = None
        for year_month in year_months:
            delay_0_y_s(2)
            # 请求数据
            while 1:
                logger.info(f'开启请求数据：{city_chinese_name}{year_month}')
                try:
                    if rps_code == 0:
                        data_name, enc_func_name, dec_func_name, text = getJS()
                    query = {'city': city_chinese_name, 'month': str(year_month)}  # 查询参数
                    sign, ctx = getParames(enc_func_name, text, query)
                    data, rps_code = getEncryptData(data_name, sign)
                    aqi_rsp_data = decrypt(data, dec_func_name, ctx)
                except:
                    logger.warning('except retry!!')
                    rps_code = 0
                else:
                    if rps_code == 200:
                        break
            # 处理数据
            dataFrame_tmp = pd.json_normalize(json.loads(aqi_rsp_data), record_path=['result', 'data', 'items'])
            dataFrame_tmp.set_index('time_point', inplace=True)

            # 增加数据
            if dataFrame is None:
                dataFrame = pd.DataFrame(dataFrame_tmp)
            else:
                dataFrame = pd.concat([dataFrame, dataFrame_tmp], axis=0)
        # 保存数据
        dataFrame_test = pd.DataFrame(dataFrame)
        write = pd.ExcelWriter(f'{city_chinese_name}.xlsx')
        dataFrame_test.to_excel(write)
        logger.info(f'保存为：{city_chinese_name}.xlsx')
        write.save()
