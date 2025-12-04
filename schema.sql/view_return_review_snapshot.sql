-- AMZ 退货分析 --
-- CREATE OR REPLACE VIEW hyy.view_return_review_snapshot as 
with raw as
(select country_name country,fasin,asin,STR_TO_DATE(review_date,'%Y-%m-%d') review_date,
review_id,2 review_source,content review_en
from HYY_DW_MYSQL.hyy.jj_review
where star <= 3

union all 
select distinct b.country,c.parent_asin fasin,a.asin,return_date review_date,
order_id review_id,0 review_source,concat(reason,": ",customer_comments) review_en
from HYY_DW_MYSQL.hyy.jj_return_orders a
left join basic_account b on a.market_id = b.gg_marketid
left join hyy.view_asin_mid_new_info c on a.asin = c.asin and b.country = c.marketplace_id
where customer_comments <> ''

union all
select distinct c.country,d.parent_asin fasin,a.asin,STR_TO_DATE(a.timestamp,'%Y-%m-%d') review_date,
a.order_id review_id,1 review_source,a.comment review_en
from HYY_DW_MYSQL.hyy.t_jj_buyer_voice_comment_incremental a
left join (select order_id,asin,max(market_id) market_id from HYY_DW_MYSQL.hyy.jj_all_orders group by order_id,asin) b 
on a.order_id = b.order_id and a.asin = b.asin
left join basic_account c on b.market_id = c.gg_marketid
left join hyy.view_asin_mid_new_info d on a.asin = d.asin and c.country = d.marketplace_id
where ((NOT EXISTS
(SELECT 1 FROM (select distinct order_id review_id,customer_comments review_en from HYY_DW_MYSQL.hyy.jj_return_orders where customer_comments <> '') b 
WHERE a.order_id = b.review_id and a.comment = b.review_en))))

select * from raw
where 
-- review_id in (select review_id from hyy.return_fact_llm where payload like '%"review_cn":""%' or payload like '%"tags":[]%')
-- and review_source = 0
-- review_id = 'R384TSBX2ZQOS'

review_id not in (select review_id from hyy.return_fact_llm where payload not like '%"review_cn":""%' and payload not like '%"tags":[]%')
and date_format(review_date,'%Y%m%d') >= 20250601
-- and country = 'US' and fasin = 'B0BGHGXYJX'
order by review_date desc,length(review_en) desc;