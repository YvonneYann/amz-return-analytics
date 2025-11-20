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
where customer_comments <> '')

select * from raw
where 
-- review_id in (select review_id from hyy.return_fact_llm where payload like '%"review_cn":""%' or payload like '%"tags":[]%')
-- and review_source = 0
-- review_id = 'R384TSBX2ZQOS'

review_id not in (select review_id from hyy.return_fact_llm where payload not like '%"review_cn":""%' and payload not like '%"tags":[]%')
and date_format(review_date,'%Y%m%d') >= 20250101
-- and country = 'US' and fasin = 'B0BGHGXYJX'
order by review_date desc,length(review_en) desc;