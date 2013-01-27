---
layout: post
title: "ngx_lua与go高并发性能对比"
date: 2013-01-28 00:46
comments: true
categories: language
---

nginx在处理高并发能力上非常出色，而go作为新时代互联网语言，在设计之初就为实现高并发。

ngx_lua由nginx来处理网络事件，并使用协程来实现非阻塞，从而实现高并发。
go语言级别提供非阻塞的api，同样使用协程来提供高并发处理。

我们来测试对比一下两者的性能。

    ngx_lua:Tengine/1.4.3+luagit+ngx_lua
    go:go1.0.3

分别实现512字节的内容的输出，对比在不同并发下的qps。

测试机器：   

    16core Intel(R) Xeon(R) CPU E5520  @ 2.27GHz  
    Linux localhost 2.6.18-164.el5 #1 SMP Tue Aug 18 15:51:48 EDT 2009 x86_64 x86_64 x86_64 GNU/Linux

使用ab进行测试，测试结果如下：

短连接  | 100                       | 200   | 500   | 1000  | 2000
------- | ------------------------- | ----- | ----- | ----- | -----
ngx_lua | qps:17329 us:2.6% sy:2.2% | 17744 | 16443 | 15852 | 13589
go      | qps:16538 us:9.1% sy:3.6% | 16546 | 15988 | 15032 | 13757


长连接  | 100                       | 200   | 500
------- | ------------------------- | ----- | -----
ngx_lua | qps:72274 us:13.8% sy:8.5 | 61204 | 61983
go      | qps:39072 us:29% sy:15%   | 38688 | 38238

**从结果中，可以看出短连接时，两者qps相差不大，而长连接时，两者相差较大。go的cpu占用比ngx_lua要高不少。另外，go在并发数增加的情况下，性能依然出色。**

相关测试代码。

lua代码：

    ngx.print("aaaaa...512...aaa")

go 代码：

    package main

    import (
        "net/http"
        "log"
        "fmt"
        "runtime"
    )

    func handler512(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Connection", "keep-alive")
        a := []byte("aaaaa...512...aaa")
        w.Header().Set("Content-Length", fmt.Sprintf("%d", len(a)))
        w.Write(a)
    }

    func main() {
        runtime.GOMAXPROCS(runtime.NumCPU())

        http.HandleFunc("/512b", handler512)

        log.Fatal(http.ListenAndServe(":8080", nil))
    }
