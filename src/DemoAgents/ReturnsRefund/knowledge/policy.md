---
title: Returns, Refunds, Replacements, and Exchanges Policy
description: Demo customer returns policy organized for category-based retrieval
ms.date: 2026-09-06
ms.topic: reference
---

## Global return requirements

Applies to every return, refund, replacement, or exchange request across all
product categories. A return decision requires a valid order that belongs to
the requesting customer, and the delivered or fulfilled item must match the
order. Final-sale items are not eligible unless they are defective, damaged,
incorrect, or protected by applicable consumer law. Refunds are issued to the
original payment method. A replacement or exchange requires available
inventory. If a required fact is missing, request the fact from the customer
or escalate for review instead of approving the return.

## Defective electronics return within 30 days

Applies to electronics such as headphones, earbuds, speakers, laptops,
tablets, smartwatches, cameras, and gaming consoles that are defective,
faulty, broken, malfunctioning, not working, stopped working, will not turn
on, will not charge, have poor sound, or arrived damaged. When the customer
reports the fault within 30 calendar days after purchase, the item is
eligible for a refund or replacement. The item does not need to be unopened.
Use the customer's stated preference when both outcomes are available and
approve the action as `approve_refund` or `approve_replacement`. If
replacement inventory is unavailable, offer a refund instead.

## Manufacturer warranty referral for older electronics

Applies to electronics such as headphones, laptops, tablets, cameras, and
speakers reported as defective, broken, or malfunctioning more than 30
calendar days after purchase. These requests are not eligible for a store
refund, replacement, or exchange. Direct the customer to the manufacturer
warranty using `refer_to_manufacturer_warranty`. Escalate for review with
`escalate_for_review` only when a mandatory consumer guarantee or extended
warranty may still apply.

## Electronics exchange for wrong color or model variant

Applies when a customer wants to exchange an electronic product such as
headphones, a phone, a laptop, a smartwatch, or a tablet for a different
color, storage size, capacity, or model variant. The item must be unused,
unopened, and complete with original accessories and packaging, and the
request must be within 30 calendar days after purchase. Approve as
`approve_exchange` when the requested variant is in stock. If the requested
variant is unavailable, offer a refund. Opened or used electronics are not
eligible for a variant exchange and must use `reject_exchange`.

## Electronics return for changed mind or unwanted purchase

Applies when a customer wants to return an electronic product such as
headphones, a speaker, a camera, or a smartwatch because they no longer want
it, changed their mind, or bought it by accident. The item must be unused,
unopened, and complete with original accessories, and the request must be
within 14 calendar days after purchase. Approve as `approve_refund`. Opened
or used electronics are not eligible for a preference return and must use
`reject_return`.

## Clothing exchange for wrong size or wrong color

Applies to clothing, apparel, jackets, shirts, dresses, jeans, and shoes when
the customer wants to exchange the item because it does not fit, is the
wrong size, is the wrong color, or looks different from expectation. The
item must be unworn, unwashed, and fitted with the original tags, and the
request must be within 30 calendar days after purchase. Approve as
`approve_exchange` when the requested size or color is in stock. If the
requested variant is unavailable, offer a refund. Worn, washed, or altered
clothing is not eligible and must use `reject_exchange`.

## Defective, damaged, or incorrect clothing item

Applies to clothing, apparel, and shoes reported as defective, torn, with a
broken zipper or missing button, damaged on delivery, stained, or shipped as
the wrong item. When the customer reports the issue within 30 calendar days
after purchase, the item is eligible for a refund or replacement. Original
tags are not required when the defect or shipment error is verified. Use the
customer's stated preference and approve as `approve_refund` or
`approve_replacement`.

## Clothing return for changed mind or unwanted purchase

Applies when a customer wants to return clothing, apparel, or shoes because
they no longer want the item, changed their mind, or received it as an
unwanted gift. The item must be unworn, unwashed, and fitted with the
original tags, and the request must be within 30 calendar days after
purchase. Approve as `approve_refund`. Items that do not meet the condition
requirements must use `reject_return`.

## Damaged or incorrect furniture on delivery

Applies to furniture such as chairs, sofas, tables, desks, beds, and
shelving reported as damaged on delivery, arrived broken, has scratches or
dents, missing parts, or is the wrong item. When the customer reports the
issue within 7 calendar days after delivery, the item is eligible for a
replacement or refund. Approve the customer's preferred outcome after the
damage or shipment error is verified, using `approve_replacement` or
`approve_refund`.

## Furniture return for changed mind or wrong fit

Applies when a customer wants to return furniture such as a chair, sofa,
table, desk, or bed because they no longer want it, changed their mind, or
the size does not fit their space. The item must be unassembled, unused, and
in the original packaging, and the request must be within 30 calendar days
after purchase. Return shipping or collection fees may be deducted from the
refund. Assembled or used furniture is not eligible. Approve an eligible
request as `approve_refund`; otherwise use `reject_return`.

## Furniture return window expiry

Applies to furniture return requests made more than 30 calendar days after
purchase for reasons other than a manufacturing defect. These requests are
not eligible for a refund, replacement, or exchange and must use
`reject_return_window_expired`. Suspected manufacturing defects on furniture
after the return window may be escalated for warranty review using
`escalate_for_review`.

## Defective, damaged, or incorrect personal care product

Applies to personal-care products such as electric toothbrushes, shavers,
hair dryers, trimmers, and skincare devices reported as defective, faulty,
broken, malfunctioning, damaged on delivery, or shipped as the wrong item.
When the customer reports the issue within 30 calendar days after purchase,
the item is eligible for a refund or replacement even when opened, provided
the defect or shipment error is verified. Use the customer's stated
preference and approve as `approve_refund` or `approve_replacement`.

## Personal care return for changed mind

Applies when a customer wants to return a personal-care product such as an
electric toothbrush, shaver, hair dryer, or skincare device because they no
longer want it, changed their mind, or received it as an unwanted gift. The
item must be unopened and in its original sealed packaging, and the request
must be within 14 calendar days after purchase. Approve as `approve_refund`.
Opened or used personal-care products cannot be refunded or exchanged for
hygiene reasons and must use `reject_return`.

## Digital goods technical failure or activation problem

Applies to digital goods such as software licenses, downloadable content,
subscriptions, and online service access when the customer reports a
technical failure such as an invalid license key, activation error,
download failure, corrupted install, or the service not being provided as
purchased. When the customer reports the issue within 14 calendar days after
purchase, offer troubleshooting or replacement access first. If the issue
cannot be resolved, escalate for refund review using `escalate_for_review`.
Do not approve an automatic refund while usage status is unknown.

## Digital goods return for changed mind

Applies when a customer wants to return a digital good such as a software
license, downloadable content, subscription, or online service because they
no longer want it, changed their mind, or bought it by accident. Digital
goods are not eligible for a refund, replacement, or exchange after the
license has been activated or the content has been downloaded and must use
`reject_return`. An unused and unactivated purchase reported within 14
calendar days may be escalated for refund review using
`escalate_for_review`.