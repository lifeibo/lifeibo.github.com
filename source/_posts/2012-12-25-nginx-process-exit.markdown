---
layout: post
title: "nginx问题定位之监控进程异常退出"
date: 2012-12-25 14:33
comments: true
categories: nginx
---

nginx在运行过程中是否稳定，是否有异常退出过？这里总结几项平时会用到的小技巧。

**1\. 在error.log中查看是否有signal项，如果有，看看signal是多少。**

比如，这是一个异常退出的情况：

    $grep signal error.log

    2012/12/24 16:39:56 [alert] 13661#0: worker process 13666 exited on signal 11

如果在进程退出后，有coredump文件产生，则会打出如下日志：

    $grep signal error.log

    2012/12/24 16:39:56 [alert] 13661#0: worker process 13666 exited on signal 11 (core dumped) 

**2\. 简单方式，看进程号是否连续**

一般来说，在worker进程启动时，其进程号都是连续的（至少相差不是很远），如果有进程退出，其进程号就不一定连续。

    $ps aux | grep nginx

    lizi      7223  0.0  0.0  74844  2024 ?        Ss   13:32   0:00 nginx: master process ./nginx
    lizi      7292  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7293  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7294  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7295  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7296  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7297  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7298  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7299  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7300  0.0  0.0  78856  5468 ?        S    13:33   0:00 nginx: worker process
    lizi      7301  0.0  0.0  78856  5452 ?        S    13:33   0:00 nginx: worker process

可以看到，10个worker进程，基本从7292到7301，进程号连续。  
如下：

    $ps aux | grep nginx

    nobody    9492 16659 26 09:18 ?        01:10:41 nginx: worker process
    root      16659     1  0 Dec24 ?       00:00:00 nginx: master process ./nginx
    nobody   16663 16659 11 Dec24 ?        02:41:38 nginx: worker process
    nobody   19344 16659 24 10:18 ?        00:50:54 nginx: worker process
    nobody    25447 16659 28 07:41 ?        01:43:56 nginx: worker process 

进程号已不再连续，说明nginx可能有工作进程异常退出。

**3\. 查看dmesg系统消息。**

在man手册里面是这么描述dmesg的：

    DESCRIPTION
    dmesg is used to examine or control the kernel ring buffer.

查看dmesg是检测系统运行状态的常用手段，通常可以帮我们排查很多问题。当然，如果有进程异常退出，dmesg也可以看到。

    $dmesg

    nginx[24721]: segfault at 0000000000000001 rip 0000000000000001 rsp 00007ffff58d8180 error 14
    nginx[1729]: segfault at 0000000000000190 rip 00000000004c2d27 rsp 00007ffff58d8340 error 4
    nginx[22002]: segfault at ffffffffffffffff rip 000000001c959744 rsp 00007fff43caac18 error 6

rip表示程序退出时的ip寄存器内容，当没有core文件可用时，可根据此值以及反汇编来查找程序core的位置。

**4. 打开coredump文件。**

一般我们在程序启动前，通过`ulimit -c ulimited`来设置core文件的大小，也可以修改`/etc/security/limits.conf`文件，添加如下信息：

    admin               soft    core            1000000
    admin               hard    core            1000000

也可以直接修改nginx的配置文件，添加如下配置项：

    worker_rlimit_core 10000m;

而此时，在limit系统中，默认coredump文件会写在启动nginx时的目录，如果nginx在启动时worker进程的用户**没有权限写**到这个目录，进程在异常退出时，就无法产生coredump文件。由于nginx启动后，或者是由别人启动，我们无法知道nginx在启动时的目录，也就无法知道core文件的目录。我曾经碰到过这样的问题，通过日志查看，是coredump出来了，但却找不到coredump的文件。

这里有一个小技巧，查看`/proc/pid/cwd`可以看到进程的工作目录，而core文件会产生在工作目录。

nginx可以配置工作目录来改变默认的工作目录，于是，我们需要配置`working_directory`为目的工作目录，我们的core文件也会产生在这个目录。

    working_directory /path/to/core;

`working_directory`与编译时指定的`--prefix=/path`不同，后者表示在配置文件中所用的相对路径所生产的绝对路径。所以，`working_directory`不会影响到配置的引用路径，而仅仅是为了改变core文件的路径，当然nginx必须有写这个目录的权限，否则无法core出来。

所以，这里，我推荐的做法是，配置`worker_rlimit_core`与`working_directory`这两个指令，这样，就不需要修改操作系统的参数就可以正常core出来了。
    
以上这些是平时用到的一些技巧的总结，大家玩得开心！
