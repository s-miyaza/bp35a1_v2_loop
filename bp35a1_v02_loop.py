#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# https://qiita.com/rukihena/items/82266ed3a43e4b652adb

# 2018-11-17 Modified by shima@shakemid.com
#            To be able to run with python 3

#from __future__ import print_function

import sys
import serial
import datetime
import time
import os
import configparser
import subprocess

sleep=120.0

# Config読み込み
config = configparser.ConfigParser()
config.read(os.path.dirname(__file__) + '/config.ini', 'UTF-8')

configure = config['config']
rbid  = configure['rbid']
rbpwd = configure['rbpwd']
serialPortDev = configure['serialPortDev']
if 'ipv6' in configure :
    ipv6Addr = configure['ipv6']
if 'panid' in configure :
    panid = configure['panid']
if 'channel' in configure :
    channel = configure['channel']

if 'files' in config:
    logfiles = config['files']
    if 'debuglog' in logfiles :
        debuglog = logfiles['debuglog']
    else:
        debuglog = ''

    if 'minutelog' in logfiles :
        minutelog = logfiles['minutelog']
    else:
        minutelog = ''

    if 'integrations' in logfiles :
        integrations = logfiles['integrations']
    else:
        integrations = ''


if 'zabbix' in config :
    zabbix = config['zabbix'] 
else :
    zabbix = None

def zabbix_sender(k,w,t=0) :
    if zabbix is not None or 'commnad' in zabbix:
        cmd = [zabbix['command']] 
        if 'options' in zabbix :
            cmd += zabbix['options'].split()
        cmd.append(u"-T")
        cmd.append(u"-i")
        cmd.append(u"-")
        if t == 0 :
            t = int(time.time())
        print( zabbix['host'], k, t, w)
        arg = u"{h} {k} {t:0} {w:0}".format( h=str(zabbix['host']), k=str(k), t=int(t), w=int(w))
        writedebug( u" ".join(cmd)+arg)
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        out = p.communicate(input=arg.encode("utf8"), timeout=10)
        print(out)

def writeFile(filename,msg) :
    f = open(filename,'a')
    f.write(msg)
    f.close()

def writedebug(msg) :
    print(msg)

def writemin(msg) :
    if minutelog != '' :
        writeFile(minutelog, msg)

def writeint(msg) :
    if integrations != '' :
        writeFile(integrations, msg)


def print_power(intPower) :
    writemin(datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S ') + u" {0}".format(intPower))

def parseE7(line) :
     # 内容が瞬時電力計測値(E7)だったら
     hexPower = line[-8:]    # 最後の4バイト（16進数で8文字）が瞬時電力計測値
     intPower = int(hexPower, 16)
     #print(u"瞬時電力計測値: {0} [W]".format(intPower))
     writemin(datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S ') + u" {0}".format(intPower)+"\n")
     zabbix_sender(u'sender.power', intPower)


def get_version(ser) :
    # とりあえずバージョンを取得してみる（やらなくてもおｋ）
    cmd = "SKVER\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    line=ser.readline() # バージョン
    print(line, flush=True)

def connect(ipv6Addr, channel, panid) :
    # シリアルポート初期化
    ser = serial.Serial(serialPortDev, 115200)
    
    get_version(ser)
    
    # Bルート認証パスワード設定
    cmd = "SKSETPWD C " + rbpwd + "\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    print(ser.readline()) # OKが来るはず（チェック無し）
    sys.stdout.flush()
    
    # Bルート認証ID設定
    cmd = "SKSETRBID " + rbid + "\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    print(ser.readline()) # OKが来るはず（チェック無し）
    sys.stdout.flush()
    
    scanDuration = 6   # スキャン時間。サンプルでは6なんだけど、4でも行けるので。（ダメなら増やして再試行）
    scanRes = {} # スキャン結果の入れ物
    
    if channel is None or ipv6Addr is None or panid is None :
        # スキャンのリトライループ（何か見つかるまで）
        while not 'Channel' in scanRes.keys() :
            # アクティブスキャン（IE あり）を行う
            # 時間かかります。10秒ぐらい？
            cmd = "SKSCAN 2 FFFFFFFF " + str(scanDuration) + "\r\n"
            ser.write(cmd.encode())
    
            # スキャン1回について、スキャン終了までのループ
            scanEnd = False
            while not scanEnd :
                line = ser.readline()
                if line != b'' :
                    print(line)
    
                if line.startswith(b"EVENT 22") :
                    # スキャン終わったよ（見つかったかどうかは関係なく）
                    scanEnd = True
                elif line.startswith(b"  ") :
                    # スキャンして見つかったらスペース2個あけてデータがやってくる
                    # 例
                    #  Channel:39
                    #  Channel Page:09
                    #  Pan ID:FFFF
                    #  Addr:FFFFFFFFFFFFFFFF
                    #  LQI:A7
                    #  PairID:FFFFFFFF
                    cols = line.decode().strip().split(':')
                    scanRes[cols[0]] = cols[1]
            scanDuration+=1
    
            if 14 < scanDuration and not 'Channel' in scanRes.keys() :
                # 引数としては14まで指定できるが、7で失敗したらそれ以上は無駄っぽい
                print("スキャンリトライオーバー")
                print("0")
                sys.exit(1)  #### 糸冬了 ####

        channel = scanRes["Channel"]
        panid = scanRes["Pan ID"]  
        # MACアドレス(64bit)をIPV6リンクローカルアドレスに変換。
        # (BP35A1の機能を使って変換しているけど、単に文字列変換すればいいのではという話も？？)
        cmd = "SKLL64 " + scanRes["Addr"] + "\r\n"
        ser.write(cmd.encode())
        print(ser.readline()) # エコーバック
        ipv6Addr = ser.readline().decode().strip()
        print(ipv6Addr)
 
    # スキャン結果からChannelを設定。
    cmd = "SKSREG S2 " + channel + "\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    print(ser.readline()) # OKが来るはず（チェック無し）
    sys.stdout.flush()
    
    # スキャン結果からPan IDを設定
    cmd = "SKSREG S3 " + panid + "\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    print(ser.readline()) # OKが来るはず（チェック無し）
    sys.stdout.flush()

    # PANA 接続シーケンスを開始します。
    cmd = "SKJOIN " + ipv6Addr + "\r\n"
    ser.write(cmd.encode())
    print(ser.readline()) # エコーバック
    print(ser.readline()) # OKが来るはず（チェック無し）
    sys.stdout.flush()
    
    # PANA 接続完了待ち（10行ぐらいなんか返してくる）
    bConnected = False
    while not bConnected :
        line = ser.readline()
        print(line)
        if line.startswith(b"EVENT 24") :
            print("PANA 接続失敗")
            sys.exit(1)  #### 糸冬了 ####
            #return ser,ipAddr,bCdhh  #### 糸冬了 ####
            #ser = serial.Serial(serialPortDev, 115200)
        elif line.startswith(b"EVENT 25") :
            # 接続完了！
            bConnected = True
        elif line.startswith(b"ERXUDP") :
            cols = line.decode().strip().split(' ')
            res = cols[8]   # UDP受信データ部分
            #tid = res[4:4+4]
            seoj = res[8:8+6]
            #deoj = res[14,14+6]
            ESV = res[20:20+2]
            #OPC = res[22,22+2]
            if seoj == "028801" and ESV == "72" :
                # スマートメーター(028801)から来た応答(72)なら
                EPC = res[24:24+2]
                if EPC == "73" :
                    parse73(line)
 
    # これ以降、シリアル通信のタイムアウトを設定
    ser.timeout = 10
    
    # スマートメーターがインスタンスリスト通知を投げてくる
    # (ECHONET-Lite_Ver.1.12_02.pdf p.4-16)
    print(ser.readline()) #無視
    sys.stdout.flush()
    return(ser, ipv6Addr)


(ser, ipv6Addr) = connect(ipv6Addr, channel, panid)

# ECHONET Lite フレーム作成
# 　参考資料
# 　・ECHONET-Lite_Ver.1.12_02.pdf (以下 EL)
# 　・Appendix_H.pdf (以下 AppH)
echonetLiteFrame = b""
echonetLiteFrame += b"\x10\x81"      # EHD (参考:EL p.3-2)
echonetLiteFrame += b"\x00\x01"      # TID (参考:EL p.3-3)
# ここから EDATA
echonetLiteFrame += b"\x05\xFF\x01"  # SEOJ (参考:EL p.3-3 AppH p.3-408〜)
echonetLiteFrame += b"\x02\x88\x01"  # DEOJ (参考:EL p.3-3 AppH p.3-274〜)
echonetLiteFrame += b"\x62"          # ESV(62:プロパティ値読み出し要求) (参考:EL p.3-5)
echonetLiteFrame += b"\x01"          # OPC(1個)(参考:EL p.3-7)
echonetLiteFrame += b"\xE7"          # EPC(参考:EL p.3-7 AppH p.3-275)
echonetLiteFrame += b"\x00"          # PDC(参考:EL p.3-9)

def check(ser) :
    scanDuration = 4   # スキャン時間。サンプルでは6なんだけど、4でも行けるので。（ダメなら増やして再試行）
    cmd = "SKSCAN 2 FFFFFFFF " + str(scanDuration) + "\r\n"
    ser.write(cmd.encode())
    line = ser.readline()
    print(line)
    if line.startswith(b"EVENT 24") or line.startswith(b"EVENT 25") :
        return(0)
    else:
        return(1)
 
cnt=0
sel=0
col30=0
daily=datetime.date.today().day
print("daily:" + str(daily))
beforetime = time.time() - sleep
while True :
    
    day = datetime.date.today().day
    if daily != day or sel > 600:
        ser.close()
        ser = connect(ipv6Addr, channel, panid)
        daily = day
        print("daily:" + str(daily))

    # コマンド送信
    if time.time() - beforetime > sleep :
        command = "SKSENDTO 1 {0} 0E1A 1 {1:04X} ".format(ipv6Addr, len(echonetLiteFrame)).encode() + echonetLiteFrame + "\r\n".encode()
        print(command)
        ser.write(command)
        beforetime = time.time()
        print(ser.readline()) # エコーバック
        print(ser.readline()) # EVENT 21 が来るはず（チェック無し）
        print(ser.readline()) # OKが来るはず（チェック無し）
        print(ser.readline()) # 改行が来るはず（チェック無し）
        line = ser.readline() # ERXUDPが来るはず
        if line != b'' :
            print(line)
    else:
        line = b''
     
    # 受信データはたまに違うデータが来たり、
    # 取りこぼしたりして変なデータを拾うことがあるので
    # チェックを厳しめにしてます。
    s=0
    if line.startswith(b"ERXUDP") :
        cols = line.decode().strip().split(' ')
        res = cols[8]   # UDP受信データ部分
        #tid = res[4:4+4]
        seoj = res[8:8+6]
        #deoj = res[14,14+6]
        ESV = res[20:20+2]
        #OPC = res[22,22+2]
        if seoj == "028801" and ESV == "72" :
            # スマートメーター(028801)から来た応答(72)なら
            EPC = res[24:24+2]
            if EPC == "E7" :
                parseE7(line)
                sel=0
                col30=0
            elif EPC == "29" :
                cnt = 1
    sys.stdout.flush()
    time.sleep(1)
    sel = sel+1

ser.close()
sys.exit(0)
