import requests
from loguru import logger
from xianyu_utils.generate_sign import generate_sign    #生成签名
from xianyu_utils.cookie_extract import extract_cookie    #解析Cookie
from xianyu_utils.cookie_env_read import read_cookie_from_env    #读取Cookie
from xianyu_utils.cookie_env_write import write_cookie_to_env    #写入Cookie
import time
import json

class xianyuAPI:
    def __init__(self):
        #获取闲鱼API接口的URL
        self.url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'

        #创建一个带状态的请求客户端，如果直接写request.get，那么登录状态会丢失，这个可以保证登录状态存在
        self.session=requests.session()

        #创建发送请求会用的到的请求头
        self.session.headers.update({
            "accept": "application/json",
            # requests 默认只保证 gzip/deflate 可靠；不要包含 zstd，避免拿到二进制压缩流导致 json 解析失败
            "accept-encoding": "gzip, deflate",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.goofish.com",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Microsoft Edge\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
        })


    #获取accessToken API
    def get_accessKEy(self):
        """
        流程：
        1.构造URL，params，data。使用post请求方法，发送数据包
        2.
        """

        #构造URL，data
        url = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"
        data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"2BF53FAD-179A-46E6-960D-B1098777BD31-2218894644927"}'
        data = {"data": data_val}

        #构造sign，sign的生成方式：{token}&{t}&{app_key}&{data}
        base_t = str(int(time.time() * 1000))
        for attempt in range(3):
            #从.env文件中加载cookie，主要我们需要理由cookie里面的_m_h5_tk,来生成sign
            cookie_str = read_cookie_from_env()
            #将字符串形式的cookie化为字典形式的，能够使用post发送
            cookies = extract_cookie(cookie_str)

            if not cookies:
                logger.error("未能从 .env 读取到 XIANYU_COOKIE，或解析后为空。")
                return None

            #更新session里面的Cookies
            try:
                self.session.cookies.update(cookies)
            except Exception:
                pass

            #开始构造sign(签名)
            t = str(int(time.time() * 1000))
            m_h5_tk = cookies.get("_m_h5_tk") or cookies.get("m_h5_tk") or ""
            token = m_h5_tk.split("_")[0] if m_h5_tk else ""
            if not token:
                logger.error("cookie 中未找到 _m_h5_tk/m_h5_tk，无法生成 sign / 获取 token")
                return None
            real_sign = generate_sign(t, token, data_val)

            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": t,
                "sign": real_sign,
                "v": "1.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.taobao.idlemessage.pc.login.token",
                "sessionOption": "AutoLoginOnly",
                "spm_cnt": "a21ybx.im.0.0",
                "spm_pre": "a21ybx.home.sidebar.2.4c053da6Uu6Bn1",
                "log_id": "4c053da6Uu6Bn1",
            }

            #post向网站站发送请求，来从response里面获取accessToken
            response = self.session.post(url, params=params, data=data, cookies=cookies)

            #将返回的数据包进行json化处理
            try:
                res_json = response.json()
                print("返回的response",res_json)
            except Exception as e:
                logger.error(f"响应不是合法的 JSON: {e}，内容: {response.text}")
                return None

            #将返回的数据包进行json化处理
            msg = json.dumps(res_json, ensure_ascii=False)
            if "SUCCESS::调用成功" in msg:
                print("获取 accessToken 成功！")
                return res_json

            #判断返回的数据包是否有'SUCCESS::调用成功'，如果有，就直接返回res_json，如果没得，就继续执行这个函数
            print("未获取到 SUCCESS::调用成功，继续手动输入 Cookie 后重试。")
            cookie_new = ""
            for _ in range(3):
                cookie_new = input("请输入当前可用的 XIANYU_COOKIE（name=value; ...）：").strip()
                if cookie_new:
                    break
                logger.error("输入的 XIANYU_COOKIE 为空，请重新粘贴后回车。")

            if not cookie_new:
                logger.error("XIANYU_COOKIE 仍为空，终止。")
                return None

            try:
                write_cookie_to_env(cookie_new)
            except Exception as e:
                logger.error(f"写入 .env 的 XIANYU_COOKIE 失败: {e}")
                return None

            # 重新执行获取逻辑
            return self.get_accessKEy()

        return None

    #获取商品信息API
    def get_item_detail(self, itemID):
        """
        流程：
        1.构造请求包:url,params，data。注意params参数里面的sign(签名)的生成原则
        2.发送请求包
        3.将请求包json处理,然后看是否调用成功，若调用成功，即直接返回res_json，若没有，则输入Cookie更新，进行调用get_item_detail函数
        """
        #---------------构造请求包-------------------
        url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
        data_val='{"itemId":"'+itemID+'"}'
        data = {"data": data_val}
        #从.env环境中读取Cookie,然后从Cookie找到m_h5_tk，利用这个来生成sign

        cookie_str = read_cookie_from_env()
        cookies = extract_cookie(cookie_str)
        if not cookies:
            logger.error("未能从 .env 读取到 XIANYU_COOKIE，或解析后为空。")
            return None
        try:
            self.session.cookies.update(cookies)
        except Exception:
            pass
        t = str(int(time.time() * 1000))
        m_h5_tk = cookies.get("_m_h5_tk") or cookies.get("m_h5_tk") or ""
        token = m_h5_tk.split("_")[0] if m_h5_tk else ""
        if not token:
            logger.error("cookie 中未找到 _m_h5_tk/m_h5_tk，无法生成 sign / 获取 token")
            return None
        real_sign = generate_sign(t, token, data_val)
        #构造params
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": t,
            "sign": real_sign,
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.pc.detail",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.item.0.0",
            "spm_pre": "a21ybx.search.searchFeedList.2.246a2ba6dx4vXG",
            "log_id": "246a2ba6dx4vXG",
        }

        #-------------发送请求--------------
        response = self.session.post(url, params=params, data=data)
        res_json = response.json()

        #--------------判断response是否是我们需要的信息------------------
        msg = json.dumps(res_json, ensure_ascii=False)
        if "SUCCESS::调用成功" in msg:
            print("获取 item 成功！")
            data_obj = res_json.get("data", {}) or {}
            item_do = data_obj.get("itemDO", {}) or {}
            seller_do = data_obj.get("sellerDO", {}) or {}

            title = item_do.get("title", "")
            desc = item_do.get("desc", "")
            sold_price = item_do.get("soldPrice", "")
            original_price = item_do.get("originalPrice", "")
            transport_fee = item_do.get("transportFee", "")
            quantity = item_do.get("quantity", "")
            browse_cnt = item_do.get("browseCnt", "")
            want_cnt = item_do.get("wantCnt", "")
            item_status = item_do.get("itemStatusStr", "")

            cpv_labels = item_do.get("cpvLabels", []) or []
            cpv_map = {}
            for label in cpv_labels:
                key = str(label.get("propertyName", "")).strip()
                val = str(label.get("valueName", "")).strip()
                if key and val:
                    cpv_map[key] = val

            brand = cpv_map.get("品牌", "")
            condition = cpv_map.get("成色", "")
            size = cpv_map.get("尺码", "")

            seller_nick = seller_do.get("nick", "")
            seller_city = seller_do.get("city", "")
            seller_reply_ratio = seller_do.get("replyRatio24h", "")
            seller_reply_interval = seller_do.get("replyInterval", "")

            product_info = (
                f"商品ID：{itemID}\n"
                f"标题：{title}\n"
                f"价格：{sold_price}\n"
                f"原价：{original_price}\n"
                f"运费：{transport_fee}\n"
                f"库存：{quantity}\n"
                f"商品状态：{item_status}\n"
                f"浏览量：{browse_cnt}，想要人数：{want_cnt}\n"
                f"品牌：{brand}，成色：{condition}，尺码：{size}\n"
                f"卖家：{seller_nick}（{seller_city}），24h回复率：{seller_reply_ratio}，平均回复：{seller_reply_interval}\n"
                f"描述：{desc}"
            )

            return {
                "item_id": itemID,
                "title": title,
                "desc": desc,
                "sold_price": sold_price,
                "original_price": original_price,
                "transport_fee": transport_fee,
                "quantity": quantity,
                "browse_cnt": browse_cnt,
                "want_cnt": want_cnt,
                "item_status": item_status,
                "brand": brand,
                "condition": condition,
                "size": size,
                "seller_nick": seller_nick,
                "seller_city": seller_city,
                "seller_reply_ratio": seller_reply_ratio,
                "seller_reply_interval": seller_reply_interval,
                "product_info": product_info,
                "raw_response": res_json,
            }

        print("未获取到 SUCCESS::调用成功，继续手动输入 Cookie 后重试。")
        cookie_new = ""
        cookie_new = input("请输入当前可用的 XIANYU_COOKIE（name=value; ...）：").strip()
        # 调用write_cookie_to_env函数，将输入的Cookie写入.env文件中
        write_cookie_to_env(cookie_new)
        # 写入后继续尝试获取
        return self.get_item_detail(itemID)


if __name__ == '__main__':
    api = xianyuAPI()

    # 调试：打印获取到的 accessToken（做了脱敏，避免日志泄露完整 token）
    res = api.get_accessKEy()
    try:
        token = res["data"]["accessToken"]
        token = str(token)
        masked = token[:8] + "..." + token[-8:] if len(token) > 16 else token
        print("accessToken:", masked)
    except Exception:
        print("获取 accessToken 失败，返回：", res)

    # 原来的商品详情调试
    print(api.get_item_detail("779900965184"))