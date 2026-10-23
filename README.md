# 使用说明
<b>以下所有脚本于Python 3.14版本测试通过。</b>

## 1. 2kb-padding-tool.py
<b>功能介绍</b>

将任意文件填充至2KB对齐。

<b>使用方式</b>

python 2kb-padding-tool.py <目录或文件路径>

<b>注：</b>当指定的对象为目录时，将会填充该目录下的所有文件。

## 2. paddingtools.py
<b>功能介绍</b>

将任意文件填充至指定的字节数大小。

<b>使用方式</b>

python paddingtools.py <文件/目录路径> <目标大小>

<b>注：</b>输入的目标大小参数为字节数，若输入的字节数小于文件大小，将会截断文件（此情况下需要用户二次确认）；当指定的对象为目录时，将会填充该目录下的所有文件。

## 3. TM2-alpha-tool.py
<b>功能介绍</b>

将0-255的Alpha通道值压缩至0-128（PS2平台使用的Alpha通道值）。

<b>使用方式</b>

<b>单文件：</b>python TM2-alpha-tool.py <文件名>

<b>多文件：</b>python TM2-alpha-tool.py *.tm2

<b>目录：</b>python TM2-alpha-tool.py <文件夹名>

<b>注：</b>当指定的对象为目录时，将会填充该目录下的所有文件。

## 4. g1t-export-tools.py
<b>功能介绍</b>

从文件块中读取指针，导出文件块中包含的G1T文件。

<b>使用方式</b>

python g1t-export-tools.py <输入文件名> [-o 输出文件夹]

<b>注：</b>当未输入输出文件夹参数时，导出的G1T文件将输出至脚本所在目录。

## 5. TM2字库转PNG.py
<b>功能介绍</b>

将TM2双层字库文件导出为两个PNG字库图片，理论上适用于所有PS2平台的无双类游戏。

<b>使用方式</b>（需要安装Pillow库）

pip install pillow

python TM2字库转PNG.py <文件名>

## 6. PNG转TM2字库.py
<b>功能介绍</b>

将修改好的两个PNG字库图片打包成TM2双层字库文件，理论上适用于所有PS2平台的无双类游戏。

<b>使用方式</b>（需要安装Pillow库）

pip install pillow

PNG转TM2字库.py --template <原始导出的TM2文件> --layer-a <图层A.png> --layer-b <图层B.png> -o <新打包的TM2文件>

<b>注：</b>修改字库时须确保字库颜色与导出的字库颜色一致，打包前需将PNG文件用OPTPiX iMageStudio for PS2的Color Reduction功能缩减至4色。

## 7. LZP2解包打包工具
<b>功能介绍</b>

对游戏使用的LZP2格式压缩文件进行解包/打包。

详见：https://github.com/lllljj1991/LZP2-tools/
