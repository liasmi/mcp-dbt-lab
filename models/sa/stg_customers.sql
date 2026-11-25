with source as (
    select * from {{ source('raw', 'customers') }}
),

renamed as (
    select
        customer_id,
        customer_name,
        country_code,
        signup_date
    from source
)

select * from renamed
