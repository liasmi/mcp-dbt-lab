with source as (
    select * from {{ source('raw', 'orders') }}
),

renamed as (
    select
        order_id,
        customer_id,
        order_date,
        cast(amount_usd * 100 as bigint) as amount_cents,
        status
    from source
)

select * from renamed
