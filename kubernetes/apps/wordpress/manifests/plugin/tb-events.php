<?php
/*
Plugin Name: TB Events
Description: Sends WordPress/WooCommerce events to Order API and Node-RED.
Version: 2.0
*/

define('TB_NODE_RED_URL', 'http://node-red-knative.node-red.svc.cluster.local/wp-event');
define('TB_ORDER_API_URL', 'http://order-api-knative.order-api.svc.cluster.local');
define('TB_EVENT_SECRET', 'supersecret123');

/*
 * Generic POST helper
 */
function tb_post_json($url, $event, $headers = []) {
    if (empty($event['event_type'])) return false;

    $default_headers = [
        'Content-Type' => 'application/json',
        'x-event-secret' => TB_EVENT_SECRET
    ];

    $resp = wp_remote_post($url, [
        'headers' => array_merge($default_headers, $headers),
        'body' => wp_json_encode($event),
        'timeout' => 8
    ]);

    if (is_wp_error($resp)) {
        error_log('[TB Events] wp_remote_post error: ' . $resp->get_error_message());
        return false;
    }

    $code = wp_remote_retrieve_response_code($resp);

    if ($code < 200 || $code >= 300) {
        error_log('[TB Events] HTTP status ' . $code . ' for URL: ' . $url);
        return false;
    }

    return true;
}

/*
 * Login still goes directly to Node-RED.
 */
function tb_send_login_to_node_red($event) {
    return tb_post_json(TB_NODE_RED_URL, $event);
}

/*
 * Cart and order events go to Order API.
 */
function tb_send_event_to_order_api($event, $idempotency_key) {
    return tb_post_json(
        TB_ORDER_API_URL . '/events',
        $event,
        [
            'Idempotency-Key' => $idempotency_key
        ]
    );
}

/*
 * LOGIN
 */
add_action('wp_login', function($user_login) {
    tb_send_login_to_node_red([
        'event_type' => 'login',
        'source' => 'wordpress',
        'event_id' => 'login-' . $user_login . '-' . time(),
        'user' => [
            'username' => $user_login
        ]
    ]);
}, 10, 1);

/*
 * CART ADD
 *
 * We use woocommerce_add_to_cart instead of woocommerce_cart_updated
 * because cart_updated can fire multiple times.
 */
add_action(
    'woocommerce_add_to_cart',
    function($cart_item_key, $product_id, $quantity, $variation_id, $variation, $cart_item_data) {
        if (!is_user_logged_in() || !function_exists('WC') || !WC()->cart) return;

        $u = wp_get_current_user();
        $product = wc_get_product($product_id);

        $sku = ($product && method_exists($product, 'get_sku')) ? $product->get_sku() : '';
        $name = ($product && method_exists($product, 'get_name')) ? $product->get_name() : '';

        $totalQty = 0;
        $items = [];

        foreach (WC()->cart->get_cart() as $item) {
            $item_product = $item['data'];
            $item_sku = ($item_product && method_exists($item_product, 'get_sku')) ? $item_product->get_sku() : '';
            $item_qty = (int)($item['quantity'] ?? 0);
            $totalQty += $item_qty;

            $items[] = [
                'sku' => $item_sku ?: (string)($item['product_id'] ?? ''),
                'name' => ($item_product && method_exists($item_product, 'get_name')) ? $item_product->get_name() : '',
                'qty' => $item_qty
            ];
        }

        /*
         * This key prevents duplicate handling if WooCommerce/plugin retries.
         * Same cart item addition should be handled once.
         */
        $idempotency_key = 'cart-add-' . $u->ID . '-' . $cart_item_key;

        tb_send_event_to_order_api([
            'event_type' => 'cart_add',
            'source' => 'woocommerce',
            'event_id' => $idempotency_key,
            'user' => [
                'id' => $u->ID,
                'username' => $u->user_login
            ],
            'cart' => [
                'added_product_id' => $product_id,
                'added_product_sku' => $sku ?: (string)$product_id,
                'added_product_name' => $name,
                'added_quantity' => (int)$quantity,
                'items' => $items,
                'total_qty' => $totalQty
            ]
        ], $idempotency_key);
    },
    10,
    6
);

/*
 * ORDER CREATED
 */
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

    $idempotency_key = 'woocommerce-order-' . $order_id;

    $sent = tb_send_event_to_order_api([
        'event_type' => 'order_created',
        'source' => 'woocommerce',
        'event_id' => $idempotency_key,
        'user' => [
            'id' => $user_id,
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
    ], $idempotency_key);

    if ($sent) {
        $order->update_meta_data('_tb_order_sent', '1');
        $order->save();
    }
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