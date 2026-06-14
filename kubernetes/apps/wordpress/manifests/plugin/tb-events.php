<?php
/*
Plugin Name: TB Events
Description: Sends WordPress/WooCommerce events to Node-RED.
Version: 1.0
*/

define('TB_NODE_RED_URL', 'http://node-red-knative.node-red.svc.cluster.local/wp-event');
define('TB_EVENT_SECRET', 'supersecret123');

function tb_send($event) {
    if (empty($event['event_type'])) return;

    $resp = wp_remote_post(TB_NODE_RED_URL, [
        'headers' => [
            'Content-Type' => 'application/json',
            'x-event-secret' => TB_EVENT_SECRET
        ],
        'body' => wp_json_encode($event),
        'timeout' => 5
    ]);

    if (is_wp_error($resp)) {
        error_log('[TB Events] wp_remote_post error: ' . $resp->get_error_message());
    } else {
        $code = wp_remote_retrieve_response_code($resp);
        if ($code < 200 || $code >= 300) {
            error_log('[TB Events] Node-RED HTTP status: ' . $code);
        }
    }
}

/* LOGIN */
add_action('wp_login', function($user_login) {
    tb_send([
        'event_type' => 'login',
        'source' => 'wordpress',
        'user' => [
            'username' => $user_login
        ]
    ]);
}, 10, 1);

/* CART UPDATED */
add_action('woocommerce_cart_updated', function() {
    if (!is_user_logged_in() || !function_exists('WC') || !WC()->cart) return;

    $u = wp_get_current_user();
    $items = [];
    $totalQty = 0;

    foreach (WC()->cart->get_cart() as $cart_item) {
        $product = $cart_item['data'];
        $sku = ($product && method_exists($product, 'get_sku')) ? $product->get_sku() : '';
        $qty = (int)($cart_item['quantity'] ?? 0);
        $totalQty += $qty;

        $items[] = [
            'sku' => $sku ?: (string)($cart_item['product_id'] ?? ''),
            'name' => ($product && method_exists($product, 'get_name')) ? $product->get_name() : '',
            'qty' => $qty
        ];
    }

    if ($totalQty <= 0) return;

    tb_send([
        'event_type' => 'cart_add',
        'source' => 'woocommerce',
        'user' => [
            'username' => $u->user_login
        ],
        'cart' => [
            'items' => $items,
            'total_qty' => $totalQty
        ]
    ]);
});

/* ORDER CREATED */
function tb_send_order_created($order_id) {
    if (!$order_id || !function_exists('wc_get_order')) return;

    $order = wc_get_order($order_id);
    if (!$order) return;

    if ($order->get_meta('_tb_order_sent') === '1') return;

    $username = 'guest';
    $user_id = $order->get_user_id();

    if ($user_id) {
        $user = get_user_by('id', $user_id);
        if ($user) {
            $username = $user->user_login;
        }
    }

    $items = [];
    $totalQty = 0;

    foreach ($order->get_items() as $item) {
        $product = $item->get_product();
        $sku = ($product && method_exists($product, 'get_sku')) ? $product->get_sku() : '';
        $qty = (int)$item->get_quantity();
        $totalQty += $qty;

        $items[] = [
            'sku' => $sku ?: (string)$item->get_product_id(),
            'name' => $item->get_name(),
            'qty' => $qty
        ];
    }

    tb_send([
        'event_type' => 'order_created',
        'source' => 'woocommerce',
        'user' => [
            'username' => $username
        ],
        'order' => [
            'id' => $order_id,
            'status' => $order->get_status(),
            'total' => (float)$order->get_total(),
            'currency' => $order->get_currency(),
            'items' => $items,
            'total_qty' => $totalQty
        ]
    ]);

    $order->update_meta_data('_tb_order_sent', '1');
    $order->save();
}

add_action('woocommerce_checkout_order_created', function($order) {
    if ($order) tb_send_order_created($order->get_id());
}, 10, 1);

add_action('woocommerce_payment_complete', function($order_id) {
    tb_send_order_created($order_id);
}, 10, 1);

add_action('woocommerce_thankyou', function($order_id) {
    tb_send_order_created($order_id);
}, 10, 1);