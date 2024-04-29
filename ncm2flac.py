# 依赖pycrypto库
import binascii
import struct
import base64
import json
import os,sys
from Crypto.Cipher import AES
#  此程序用于将网易云音乐的.ncm格式的音乐转换为  最初格式
from concurrent.futures import ThreadPoolExecutor
import time
import numpy as np
import shutil
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from mutagen.easyid3 import EasyID3
from PIL import Image
import io

def process_chunk(chunk, key_box, curThread):
    #print("线程"+str(curThread)+"正在处理数据块")
    chunk = np.frombuffer(chunk, dtype=np.uint8)
    i = np.arange(1, len(chunk) + 1) & 0xff
    j = key_box[i] + key_box[(key_box[i] + i) & 0xff]
    chunk ^= key_box[j & 0xff]
    #print("线程"+str(curThread)+"处理数据块完成")
    return chunk.tobytes()

def dump(oriPath, tarPath):
    print("正在处理"+oriPath+"...")
    core_key = binascii.a2b_hex("687A4852416D736F356B496E62617857")
    meta_key = binascii.a2b_hex("2331346C6A6B5F215C5D2630553C2728")
    unpad = lambda s: s[0:-(s[-1] if type(s[-1]) == int else ord(s[-1]))]
    f = open(oriPath, 'rb')
    header = f.read(8)
    strHeader = binascii.b2a_hex(header)
    needDecode = False
    if strHeader == b'4354454e4644414d':
        needDecode = True
    elif strHeader == b'664c614300000022': #狗屎网易云音乐的ncm格式竟然有flac头
        print("文件已经是flac格式") 
        file_path = f.name
        base_name, ext = os.path.splitext(os.path.basename(file_path))
        new_file_name = base_name + '.flac'
        new_file_path = os.path.join(tarPath, new_file_name)
        shutil.copy(file_path, new_file_path)
        return

    f.seek(2, 1)
    key_length = f.read(4)
    key_length = struct.unpack('<I', bytes(key_length))[0]
    key_data = f.read(key_length)
    key_data_array = bytearray(key_data)
    for i in range(0, len(key_data_array)): key_data_array[i] ^= 0x64
    key_data = bytes(key_data_array)
    cryptor = AES.new(core_key, AES.MODE_ECB)
    key_data = unpad(cryptor.decrypt(key_data))[17:]
    key_length = len(key_data)
    key_data = bytearray(key_data)
    key_box = bytearray(range(256))
    c = 0
    last_byte = 0
    key_offset = 0
    for i in range(256):
        swap = key_box[i]
        c = (swap + last_byte + key_data[key_offset]) & 0xff
        key_offset += 1
        if key_offset >= key_length: key_offset = 0
        key_box[i] = key_box[c]
        key_box[c] = swap
        last_byte = c
    meta_length = f.read(4)
    meta_length = struct.unpack('<I', bytes(meta_length))[0]
    meta_data = f.read(meta_length)
    meta_data_array = bytearray(meta_data)
    for i in range(0, len(meta_data_array)): meta_data_array[i] ^= 0x63
    meta_data = bytes(meta_data_array)
    meta_data = base64.b64decode(meta_data[22:])
    cryptor = AES.new(meta_key, AES.MODE_ECB)
    meta_data = unpad(cryptor.decrypt(meta_data)).decode('utf-8')[6:]
    meta_data = json.loads(meta_data)
    crc32 = f.read(4)
    crc32 = struct.unpack('<I', bytes(crc32))[0]
    f.seek(5, 1)
    image_size = f.read(4)
    image_size = struct.unpack('<I', bytes(image_size))[0]
    image_data = f.read(image_size)
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    
    file_path = f.name
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    file_name = base_name + '.' + meta_data['format']
    
    for char in illegal_chars:
        file_name = file_name.replace(char, '')
    print("歌曲名："+file_name)
    mName = os.path.join(os.path.split(tarPath)[0], file_name)
    if os.path.exists(mName):
        f.close()
        return
    m = open(mName, 'wb')
    chunk = bytearray()
    result = bytearray()

    if needDecode:
        curThread = 0
        key_box = np.array(key_box, dtype=np.uint8)

        with ThreadPoolExecutor() as executor:
            futures = []
            while True:
                chunk = bytearray(f.read(0xA00000))
                if not chunk:
                    break
                
                curThread += 1
                future = executor.submit(process_chunk, chunk, key_box, curThread)
                futures.append(future)
        
        for future in futures:
            chunk = future.result()
            result.extend(chunk)
        print("处理完成，写入中...")
    else:
        result = bytearray(f.read())
    m.write(result)


#'musicId':
#'371250'
#'musicName':
#'下雨回家唱歌'
#'artist':
#[['七八点', '12603']]
#'albumId':
#'36810'
#'album':
#'屋顶上的猫'
#'albumPicDocId':
#'81363860471488'
#'albumPic':
#'https://p4.music.126.net/qMr8SprFDhyyeStNWPs9Mg==/81363860471488.jpg'
#'bitrate':
#4999000
#'mp3DocId':
#'65d8cdcd96782ee9741e399efb6fe934'
#'duration':
#156966

    # 获取文件的扩展名
    extension = os.path.splitext(mName)[1]

    # 根据扩展名创建相应的对象
    if extension.lower() == ".flac":
        audio = FLAC(mName)
        # 设置元数据
        audio["musicName"] = meta_data["musicName"]
        audio["artist"] = getArtist(meta_data["artist"])
        audio["album"] = meta_data["album"]

        if image_size > 0 :
            # 创建一个Image对象
            image = Image.open(io.BytesIO(image_data))

            # 创建一个Picture对象
            pic = Picture()
            pic.data = image_data
            pic.type = 3  # 3表示封面前面
            pic.mime = "image/jpeg"  # 或者 "image/png"
            pic.width, pic.height = image.size
            pic.depth = 24  # 颜色深度

            # 将图片添加到FLAC文件的元数据
            audio.add_picture(pic)

        # 保存元数据到文件
        audio.save()

    elif extension.lower() == ".mp3":
        
        if image_size > 0 :
            # 创建一个ID3对象
            id3 = ID3(mName)

            # 创建一个Image对象
            image = Image.open(io.BytesIO(image_data))

            # 创建一个APIC对象
            apic = APIC(
                encoding=3,  # 3表示utf-8
                mime='image/jpeg',  # 或者'image/png'
                type=3,  # 3表示封面前面
                desc=u'Cover',
                data=image_data
            )

            # 将APIC对象添加到ID3对象
            id3.add(apic)

            # 保存ID3对象到文件
            id3.save(mName)
        
        # 创建一个EasyID3对象
        audio = EasyID3(mName)
        audio["title"] = meta_data["musicName"]
        audio["artist"] = getArtist(meta_data["artist"])
        audio["album"] = meta_data["album"]

        # 保存元数据到文件
        audio.save()

    m.close()
    f.close()
 
def getArtist(artist):
    artistName = ""
    for i in range(0, len(artist)):
        artistName += artist[i][0]
        if i != len(artist)-1:
            artistName += ", "
    return artistName

if __name__ == '__main__':
    #oriPath = input("输入源文件文档路径之后按回车:")
    #tarPath = input("输入目标文档路径后按回车:")
    oriPath = r"C:\Users\Administrator\Desktop\test1"
    tarPath = r"C:\Users\Administrator\Desktop\test2"
    if tarPath[-1] != '/' or tarPath[-1] != '\\':
        tarPath += '\\'

    # if len(sys.argv) > 1:
    #     for file_path in sys.argv[1:]:
    #   循环遍历所有的歌曲  只能进行一层文件夹下是歌曲
    
    #try:
    #    list = os.listdir(oriPath)
    #    num = len(list)
    #    print("共有"+str(num)+"首歌")
    #    print("正在转换...")
    #    for i in range(0, len(list)):
    #        print("正在转换第"+str(i+1)+"/"+str(num)+"首")
    #        path = os.path.join(oriPath, list[i])
    #        if os.path.isfile(path):
    #            startTime = time.time()
    #            dump(path, tarPath)
    #            endTime = time.time()
    #            duration = endTime - startTime
    #            print("第"+str(i+1)+"/"+str(num)+"首歌转换完成，用时"+str(duration)+"秒")
    #    input("转换完成!按任意键退出。。。")
    #except:
    #    pass
    #    print("Usage: python ncmdump.py \"File Name\"")
    
    list = os.listdir(oriPath)
    num = len(list)
    print("共有"+str(num)+"首歌")
    print("正在转换...")
    for i in range(0, len(list)):
        print("正在转换第"+str(i+1)+"/"+str(num)+"首")
        path = os.path.join(oriPath, list[i])
        if os.path.isfile(path):
            startTime = time.time()
            dump(path, tarPath)
            endTime = time.time()
            duration = endTime - startTime
            print("第"+str(i+1)+"/"+str(num)+"首歌转换完成，用时"+str(duration)+"秒")
    input("转换完成!按回车键退出。。。")
