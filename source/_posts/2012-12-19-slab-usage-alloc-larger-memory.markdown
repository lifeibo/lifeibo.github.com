---
layout: post
title: "nginx中slab分配大内存的陷阱"
date: 2012-12-19 17:57
comments: true
categories: nginx
keywords: nginx, slab, 源码, 内存
---


我们在开发nginx模块时，需要很小心，nginx里面有很多陷阱是我们需要注意的。之前有人提到过slab分配器在使用时，不适合大内存分配，否则会出现分配不出内存的现象。

nginx一般使用slab来管理共享内存，在程序启动时，很分配好需要共享的内存，然后使用slab来进行初始化，之后就交给slab来管理这段内存。slab的源码分析与合适，在我之前的博客里面有分析过。这次我们针对性的看看，为什么会出现分配不出内存的现象。

分配内存时，会调用`ngx_slab_alloc_locked`，在这个函数里面会先判断size是否大于`ngx_slab_max_size`，代码如下。

    void *
    ngx_slab_alloc_locked(ngx_slab_pool_t *pool, size_t size)
    {
        size_t            s;
        uintptr_t         p, n, m, mask, *bitmap;
        ngx_uint_t        i, slot, shift, map;
        ngx_slab_page_t  *page, *prev, *slots;

        /* 判断大小 */
        if (size >= ngx_slab_max_size) {

            ngx_log_debug1(NGX_LOG_DEBUG_ALLOC, ngx_cycle->log, 0,
                           "slab alloc: %uz", size);

            /* 直接分配页 */
            page = ngx_slab_alloc_pages(pool, (size + ngx_pagesize - 1)
                    >> ngx_pagesize_shift);
            if (page) {
                p = (page - pool->pages) << ngx_pagesize_shift;
                p += (uintptr_t) pool->start;

            } else {
                p = 0;
            }

            goto done;
        }

        ...

    }

<!--more-->

`ngx_slab_max_size`在nginx调用`ngx_slab_init`的时候初始化为`ngx_pagesize / 2`。我们知道，slab会将整块的内存分成pages，每个pages大小为`ngx_pagesize`，slab在分配小内存时，会将一个page拆分成多个小块进行分配，而如果我们分配的内存大于`ngx_pagesize / 2`时，slab是没办法进行拆分的，所以当我们分配的内存大于`ngx_slab_max_size`时，直接分配页内存就可以了（因为不需要进行拆分）。所以这里直接调用`ngx_slab_alloc_pages`来分配内存。`ngx_slab_alloc_pages`的代码如下：

    static ngx_slab_page_t *
    ngx_slab_alloc_pages(ngx_slab_pool_t *pool, ngx_uint_t pages)
    {
        ngx_slab_page_t  *page, *p;

        for (page = pool->free.next; page != &pool->free; page = page->next) {

            /* 判断当前页还能分配多少连续的页 */
            if (page->slab >= pages) {

                if (page->slab > pages) {
                    /* 重新设置剩下还能分配的连续空间 */
                    page[pages].slab = page->slab - pages;
                    page[pages].next = page->next;
                    page[pages].prev = page->prev;

                    p = (ngx_slab_page_t *) page->prev;
                    p->next = &page[pages];
                    page->next->prev = (uintptr_t) &page[pages];

                } else {
                    /* 剩下连续的pages正好够用 */
                    p = (ngx_slab_page_t *) page->prev;
                    p->next = page->next;
                    page->next->prev = page->prev;
                }

                page->slab = pages | NGX_SLAB_PAGE_START;
                page->next = NULL;
                page->prev = NGX_SLAB_PAGE;

                /* 如果只需要分配一个页，则直接返回 */
                if (--pages == 0) {
                    return page;
                }

                /* 否则将剩下所需要的页设置占用标记 */
                for (p = page + 1; pages; pages--) {
                    p->slab = NGX_SLAB_PAGE_BUSY;
                    p->next = NULL;
                    p->prev = NGX_SLAB_PAGE;
                    p++;
                }

                return page;
            }
        }

        ngx_slab_error(pool, NGX_LOG_CRIT, "ngx_slab_alloc() failed: no memory");

        return NULL;
    }

从上面的代码中我们可以看到，在空闲页中`p->slab`用于标记剩下连续，连接页的第一个页会设置这个值。所以在slab初始化之后，第一个页的slab被赋值为所有页的数量。在使用过程中，由于经常alloc与free，会造成连续空闲页变得断断续续，当没有连续的所需要的空闲页进行分配时，就会出现内存无法分配的问题。所以，使用slab进行大内存分配时，就会出现内存无法分配的现象。所以，我们在使用中，应该避免使用slab进行大内存的分配。

