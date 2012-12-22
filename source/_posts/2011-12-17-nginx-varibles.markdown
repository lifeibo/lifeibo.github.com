---
layout: post
title: "nginx源码分析之变量"
date: 2011-12-17 18:51
comments: true
categories: nginx
---

nginx中的变量在nginx中的使用非常的多，正因为变量的存在，使得nginx在配置上变得非常灵活。

我们知道，在nginx的配置文件中，配合变量，我们可以动态的得到我们想要的值。最常见的使用是，我们在写`access_log`的格式时，需要用到多很多变量。
而这些变量是如何工作的呢？我们可以输出哪些变量？我们又怎么才能输出自己想要的内容呢？当然，我们可能还想知道，如何在我们的模块里面去使用变量，如何添加变量，获取变量的值，以及设置变量的内容？如何使用，以及需要注意些什么？

问题一大堆，那接下来，就让我们一起去一探nginx源码的秘密。

我要讲的内容

1. 变量的分类
2. 相关结构
3. 模块中操作变量的函数
4. 变量的实现源码及流程


##1. 变量的分类##

站在使用者的角度来看，我们在配置文件中可以看到：

1. set添加的变量(变量名由用户设定)
2. nginx功能模块中添加的变量，如geo模块(变量名由用户设定)
3. nginx内建的变量(变量名已由nginx设定好，可以看`ngx_http_core_variables`结构)
4. 有一定规则的变量，如”`http_host`”等(有相同前缀，表示某一类变量)，我们就称为规则变量吧

从这里，也解决我们的问题，在配置`access_log`时，我们可以配置哪些变量，是否是用户添加的变量，是否是内建变量在`ngx_http_core_variables`中有，其次，是否是规则变量，另外，如果想输出自己的内容，那只能写模块自己添加一个变量了，或者hack nginx在`ngx_http_core_variables`中添加一个变量。

<!--more-->

从nginx内部实现上来看，变量可分为：

1. hash过的变量
2. 未hash过的变量，变量有设置`NGX_HTTP_VAR_NOHASH`
2. 未hash过的变量，但有一定规则的变量，如以这些串开头的：”`http_`”,”`sent_http_`”,”`upstream_http_`”,”`cookie_`”,”`arg_`”

我们在模块里面可以通过`ngx_http_add_variable`来添加一个变量，在后面的介绍中我们可以看到。而我们添加的变量，最好不要是以这些规则开头的变量，否则就有可能会覆盖掉这些规则的变量。

从变量获取者来看，可以分为索引变量与未索引的变量。

1. 索引变量，我们通过`ngx_http_get_variable_index`来获得一个索引变量的索引号。然后可以通过`ngx_http_get_indexed_variable`与`ngx_http_get_flushed_variable`来获取索引过变量的值。如果要索引某个变量，则只能在配置文件初始化的时候来设置。`ngx_http_get_variable_index`不会添加一个真正的变量，在配置文件初始化结束时，会检查该变量的合法性。索引过的变量，将会有缓存等特性(缓存在`r->variables`中)。
2. 未索引过的变量，则只能通过`ngx_http_get_variable`来获取变量的值。


##2. 相关结构##

接下来，我们就要开始进入源码的世界了，先看看几个关键结构：

    // ngx_variable_value_t即变量的结果，变量的值
    typedef struct {
        unsigned    len:28;     

        unsigned    valid:1;    // 当前变量是否合法
        unsigned    no_cacheable:1; // 当前变量是否可以缓存，缓存过的变量将只会调用一次get_handler函数
        unsigned    not_found:1;// 变量是否找到
        unsigned    escape:1;

        u_char     *data;       // 变量的数据
    } ngx_variable_value_t;

    // 变量本身的信息
    struct ngx_http_variable_s {
        ngx_str_t                     name;     // 变量的名称
        ngx_http_set_variable_pt      set_handler;  // 变量的设置函数
        ngx_http_get_variable_pt      get_handler;  // 变量的get函数
        uintptr_t                     data;     // 传给get与set_handler的值
        ngx_uint_t                    flags;    // 变量的标志
        ngx_uint_t                    index;    // 如果有索引，则是变量的索引号
    };

    // 在ngx_http_core_module的配置文件中保存了所使用的变量信息
    typedef struct {
        ngx_hash_t                 variables_hash;     // 变量的hash表
        ngx_array_t                variables;         // 索引变量的数组
        ngx_hash_keys_arrays_t    *variables_keys;       // 变量的hash数组
    } ngx_http_core_main_conf_t;

    // 变量在每个请求中的值是不一样的，也就是说变量是请求相关的
    // 所以在ngx_http_request_s中有一个变量数组，主要用于缓存当前请求的变量结果
    // 从而可以避免一个变量的多次计数，计算过一次的变量就不用再计算了
    // 但里面保存的一定是索引变量的值，是否缓存，也要由变量的特性来决定
    struct ngx_http_request_s {
        ngx_http_variable_value_t        *variables;
    }

##3. 模块中操作变量的函数##

那么，在模块中，我们要如何使用一个变量呢？在前面讲分类的时候，我们也提到过了，这里再总结并细说一下：
首先，如果要添加一个变量，我们需要调用`ngx_http_add_variable`函数来添加一个变量。添加时需要指明变量的名称就行了。

    // name: 即变量的名字
    // flags: 如果同一个变量要多次添加，则flags应该设置NGX_HTTP_VAR_CHANGEABLE
    // 否则，多次添加将会提示重复
    // flags表示可以是：NGX_HTTP_VAR_CHANGEABLE
    //                 NGX_HTTP_VAR_NOCACHEABLE
    //                 NGX_HTTP_VAR_INDEXED
    //                 NGX_HTTP_VAR_NOHASH
    ngx_http_variable_t *ngx_http_add_variable(ngx_conf_t *cf, ngx_str_t *name, ngx_uint_t flags);

然后，要获取变量，如果要高效一点，我们可以先将该变量放到索引数组里面，通过`ngx_http_get_variable_index`来添加一个变量的索引：

    // name: 即nginx支持的任意变量名
    // 返回该变量的索引
    ngx_int_t ngx_http_get_variable_index(ngx_conf_t *cf, ngx_str_t *name);

不过，要注意的是，添加的变量必须是nginx支持的已存在的变量。即如果是hash过的变量，则一定是通过`ngx_http_add_variable`添加的变量，否则，一定是规则变量，如”`http_host`”。当然，在解析配置文件的时候，变量不一定是要先通过`ngx_http_add_variable`然后才能获取索引，这个是不需要有顺序保证的。nginx会将在最后配置文件解析完成后，去验证这些索引变量的合法性，在`ngx_http_variables_init_vars`函数中可以看到，我们在后面具体再分析。
所以，可以看到，获取索引的操作，一定是要在解析配置文件的过程是进行的， 一旦配置文件解析完成后，索引变量不能再添加。在获取索引号后，我们需要保存该索引号，以便在后面通过索引号来获取变量。

那么，索引变量的获取，可以通过`ngx_http_get_indexed_variable`与`ngx_http_get_flushed_variable`来获取，两个函数间的区别，我们后面再介绍：

    ngx_http_variable_value_t *ngx_http_get_indexed_variable(ngx_http_request_t *r, ngx_uint_t index);  
    ngx_http_variable_value_t *ngx_http_get_flushed_variable(ngx_http_request_t *r, ngx_uint_t index);  

而如果没有索引过的变量，则只能通过`ngx_http_get_variable`函数来获取了。

    // key 由ngx_hash_strlow来计算  
    ngx_http_variable_value_t *ngx_http_get_variable(ngx_http_request_t *r, ngx_str_t *name, ngx_uint_t key);  

可以看到，key是通过ngx_hash_strlow来计算的，所以变量名是没有大小写区分的。

最后，通过获取变量的函数，我们可以看到，变量是与请求相关的，也就是获取的变量都是与当前请求相关的。

##4. 变量的实现源码及流程##

那接下来，我们就来看看nginx在源码中的实现吧！

_初始化_：

首先，在数据结构中，我们知道`ngx_http_core_main_conf_t`中保存了变量相关的一些信息，我们添加的变量key放在`cmcf->variables_keys`中，而cmcf->variables保存变量的索引结构，`cmcf->variables_hash`则保存着变量hash过的结构。

`ngx_http_add_variable`添加变量的时候，会先放到`cmcf->variables_keys`中，然后在解析完后，再生成hash结构体。

那么，`ngx_http_core_module`的preconfiguration阶段，调用`ngx_http_variables_add_core_vars`初始化变量的数据结构，然后再添加`ngx_http_core_variables`结构中的变量。所以可以看出，nginx中内建的变量是在这个数组里面的。
然后在解析其它模块的配置文件时，会通过`ngx_http_add_variable`函数来添加变量：

    ngx_http_variable_t *
    ngx_http_add_variable(ngx_conf_t *cf, ngx_str_t *name, ngx_uint_t flags)
    {
        // 先检查变量是否在已添加
        key = cmcf->variables_keys->keys.elts;
        for (i = 0; i < cmcf->variables_keys->keys.nelts; i++) {
            if (name->len != key[i].key.len
                    || ngx_strncasecmp(name->data, key[i].key.data, name->len) != 0)
            {
                continue;
            }

            v = key[i].value;

            // 如果已添加，并且是不可变的变量，则提示变量的重复添加
            // 其它NGX_HTTP_VAR_CHANGEABLE就是为了让变量的重复添加时不出错，都指向同一变量
            if (!(v->flags & NGX_HTTP_VAR_CHANGEABLE)) {
                ngx_conf_log_error(NGX_LOG_EMERG, cf, 0,
                        "the duplicate \"%V\" variable", name);
                return NULL;
            }
            // 如果变量已添加，并且有NGX_HTTP_VAR_CHANGEABLE表志，则直接返回
            return v;
        }

        // 添加这个变量
        v = ngx_palloc(cf->pool, sizeof(ngx_http_variable_t));

        v->name.len = name->len;

        // 注意，变量名不区分大小写
        ngx_strlow(v->name.data, name->data, name->len);

        rc = ngx_hash_add_key(cmcf->variables_keys, &v->name, v, 0);

        if (rc == NGX_ERROR) {
            return NULL;
        }

        return v;
    }

在添加完变量后，我们需要设置变量的`get_handler`与`set_handler`。`get_handler`是当我们在获取变量的时候调用的函数，在该函数中，我们需要设置变量的值。而在`set_handler`则是用于主动设置变量的值。`get_handler`与`set_handler`的区别是：`get_handler`是在变量使用时获取值，而`set_handler`则是变量会主动先设置好，在使用的时候就不用再算了。目前，`set`指令，设置一个变量的值是用的`set_handler`。
在需要获取变量的模块中，可以通过`ngx_http_get_variable_index`来得到变量的索引，这个函数工作很简单，就是在`ngx_http_core_main_conf_t`的variables中添加一个变量，并返回该变量在数组中的索引号。源码就不展示了。然后，在解析配置文件之后，在`ngx_http_block`中通过`ngx_http_variables_init_vars`函数来初始化变量，在`ngx_http_variables_init_vars`中，会做两个事情，检查索引变量，以及初始化变量的hash表。首先，对索引数组中的每一个元素，会先检查是否在`ngx_http_core_main_conf_t`的`variables_keys`中出现，即是否是添加过的，然后再检查是否是有特定规则的变量，如”`http_host`”，如果都不是，则说明该变量是不存在的，该索引会对应于一个不存在的变量，所以就会提示错误，程序无法启动。然后，如果变量有设置`NGX_HTTP_VAR_NOHASH`，则会跳过该变量，不进行hash，再对hash过的变量建立hash表。

_在请求中:_
当一个请求过来时，在ngx_http_init_request函数中，即请求初始化的时候，会建立一个与ngx_http_core_main_conf_t中的变量索引数组variables大小一样的数组。r->variables有两个作用，一是为了缓存变量的值，二是可以在创建子请求时，父请求给子请求传递一些信息。注意，变量的值是与当前请求相关的，所以每个请求里面会不一样。
然后在模块里面ngx_http_get_indexed_variable和ngx_http_get_flushed_variable，这两个函数的代码还是要小讲一下：

    ngx_http_variable_value_t *
    ngx_http_get_indexed_variable(ngx_http_request_t *r, ngx_uint_t index)
    {
        ngx_http_variable_t        *v;
        ngx_http_core_main_conf_t  *cmcf;

        cmcf = ngx_http_get_module_main_conf(r, ngx_http_core_module);

        // 变量已经获取过了，就不再计算变量的值，直接返回
        if (r->variables[index].not_found || r->variables[index].valid) {
            return &r->variables[index];
        }

        // 如果变量是初次获取，则调用变量的get_handler来得到变量值，并缓存到r->variables中去

        v = cmcf->variables.elts;

        if (v[index].get_handler(r, &r->variables[index], v[index].data)
                == NGX_OK)
        {
            if (v[index].flags & NGX_HTTP_VAR_NOCACHEABLE) {
                r->variables[index].no_cacheable = 1;
            }

            return &r->variables[index];
        }

        // 变量获取失败，设置为不合法，以及未找到
        // 注意我们在调用完本函数后，需要检查函数的返回值以及这两个属性
        r->variables[index].valid = 0;
        r->variables[index].not_found = 1;
        return NULL;
    }

    ngx_http_variable_value_t *
    ngx_http_get_flushed_variable(ngx_http_request_t *r, ngx_uint_t index)
    {
        ngx_http_variable_value_t  *v;

        v = &r->variables[index];

        if (v->valid) {
            // 变量已经获取过了，而且是合法的并且可缓存的，则直接返回
            if (!v->no_cacheable) {
                return v;
            }

            // 否则，清除标志，并再次获取变量的值
            v->valid = 0;
            v->not_found = 0;
        }

        return ngx_http_get_indexed_variable(r, index);
    }

注意：`ngx_http_get_flushed_variable`会考虑到变量的cache标志，如果变量是可缓存的，则只有在变量是合法的时才返回变量的值，否则重新获取变量的值。而`ngx_http_get_indexed_variable`则不管变量是否可缓存，只要获取过一次了，不管是否成功，则都不会再获取了。最后，如果是未索引的变量，我们可以通过`ngx_http_get_variable`函数来得到变量的值。`ngx_http_get_variable`做的工作：

1. 变量是hash过的，而且变量有索引过，则调用`ngx_http_get_flushed_variable`来得到变量值。
2. 变量hash过，未索引过，则调用变量的`get_handler`来获取变量，注意，此时每次调用变量，都将会调用`get_handler`来计算变量的值，然后返回该值。注意因为只有索引过的变量的值才会缓存到`ngx_http_request_t`的variables中去，所以变量的添加方要注意，如果当前变量是可缓存的，要将该变量建立索引，即调用完`ngx_http_add_variable`后，再调用`ngx_http_get_variable_index`来将该变量建立索引。
3. 特定规则的变量，”http\_”开头的会调用`ngx_http_variable_unknown_header_out`函数，”`upstream_http_`”开头的会调用`ngx_http_upstream_header_variable`函数，”cookie\_”开头的会调用`ngx_http_variable_cookie`函数，”arg\_”开头的会调用`ngx_http_variable_argument`函数。
4. 变量未找到，设置变量

至此，变量的整个流程差不多就完了，另外还有一个要注意的是，在创建子请求时候的变量。在`ngx_http_subrequest`函数中，我们可以看到，子请求的variables是直接指向父请求的variables数组的，所以子请求与父请求是共享variables数组的，这样父子请求就可以传递变量的值。但正因为如此，我们在使用父子请求的时候会产生一些问题，如果一个父请求创建多个子请求，他们之间获取同一个变量时，会有很明显的干扰，因为每个请求的环境是不一样的，这样获取的值也是不一样的。

好吧，变量也简单的介绍了一下。
