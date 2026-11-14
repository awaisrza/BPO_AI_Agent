<?php
/**
 * AI Fronter — set test lead hopper status READY after dashboard add_lead (NEW).
 *
 * Install once on ViciDial:
 *   cp ai_fronter_fix_hopper.php /var/www/html/vicidial/
 *   echo 'your-long-secret' > /etc/ai-fronter/hopper_fix.secret
 *   chmod 600 /etc/ai-fronter/hopper_fix.secret
 *
 * Dashboard .env.local:
 *   VICIDIAL_HOPPER_FIX_SECRET=your-long-secret
 */
header('Content-Type: text/plain; charset=utf-8');

$secretFile = '/etc/ai-fronter/hopper_fix.secret';
$expected = is_readable($secretFile) ? trim((string) file_get_contents($secretFile)) : '';
if ($expected === '' || !hash_equals($expected, (string) ($_GET['secret'] ?? ''))) {
    http_response_code(403);
    echo "ERROR: forbidden\n";
    exit;
}

$campaign = preg_replace('/[^a-zA-Z0-9_\-]/', '', (string) ($_GET['campaign_id'] ?? 'test_cam'));
$pcode = preg_replace('/\D/', '', (string) ($_GET['phone_code'] ?? ''));
$pnum = preg_replace('/\D/', '', (string) ($_GET['phone_number'] ?? ''));
$action = (string) ($_GET['action'] ?? 'hopper');
$noPhoneActions = ['preflight', 'load_hopper', 'clear_hopper', 'set_remote_agent'];
if ($campaign === '' || (!in_array($action, $noPhoneActions, true) && ($pcode === '' || $pnum === ''))) {
    http_response_code(400);
    echo "ERROR: campaign_id, phone_code, phone_number required\n";
    exit;
}

$conf = '/etc/astguiclient.conf';
if (!is_readable($conf)) {
    http_response_code(500);
    echo "ERROR: astguiclient.conf not found\n";
    exit;
}

$cfg = [];
foreach (file($conf) as $line) {
    if (preg_match('/^\s*(\w+)\s*=>\s*(.*)$/', trim($line), $m)) {
        $cfg[$m[1]] = trim($m[2]);
    }
}
$user = $cfg['VARDB_user'] ?? 'cron';
$pass = $cfg['VARDB_pass'] ?? '';
$db = $cfg['VARDB_database'] ?? 'asterisk';
$host = $cfg['VARDB_server'] ?? 'localhost';

$mysqli = @new mysqli($host, $user, $pass, $db);
if ($mysqli->connect_error) {
    http_response_code(500);
    echo "ERROR: db connect\n";
    exit;
}

if ($action === 'preflight') {
    ai_fronter_preflight($mysqli, $campaign, preg_replace('/\D/', '', (string) ($_GET['agent_user'] ?? '6666')));
    exit;
}
if ($action === 'load_hopper') {
    ai_fronter_load_hopper($mysqli, $campaign);
    exit;
}
if ($action === 'clear_hopper') {
    $c = $mysqli->real_escape_string($campaign);
    $mysqli->query("DELETE FROM vicidial_hopper WHERE campaign_id='{$c}' AND status IN ('READY','NEW')");
    echo "OK: hopper cleared ({$mysqli->affected_rows} lead(s)) campaign={$campaign}\n";
    exit;
}
if ($action === 'set_remote_agent') {
    // Dashboard API user often lacks modify_remote_agents — toggle via MySQL instead.
    $agent = preg_replace('/\D/', '', (string) ($_GET['agent_user'] ?? '6666'));
    $status = strtoupper((string) ($_GET['status'] ?? 'ACTIVE'));
    if ($status !== 'ACTIVE' && $status !== 'INACTIVE') {
        echo "ERROR: status must be ACTIVE or INACTIVE\n";
        exit;
    }
    if ($agent === '') {
        echo "ERROR: agent_user required\n";
        exit;
    }
    $a = $mysqli->real_escape_string($agent);
    $c = $mysqli->real_escape_string($campaign);
    $s = $mysqli->real_escape_string($status);
    $mysqli->query(
        "UPDATE vicidial_remote_agents SET status='{$s}', campaign_id='{$c}', number_of_lines=1
         WHERE user_start='{$a}'"
    );
    if ($mysqli->affected_rows < 1) {
        $check = $mysqli->query("SELECT status, campaign_id FROM vicidial_remote_agents WHERE user_start='{$a}'");
        $row = $check ? $check->fetch_assoc() : null;
        if (!$row) {
            echo "ERROR: remote agent {$agent} not found\n";
            exit;
        }
        // Already at the requested status/campaign — treat as success.
        echo "OK: remote agent {$agent} already {$row['status']} on {$row['campaign_id']}\n";
        exit;
    }
    if ($status === 'INACTIVE') {
        $mysqli->query(
            "UPDATE vicidial_live_agents SET status='PAUSED', lead_id=0, uniqueid='', callerid='', channel='', comments=''
             WHERE user='{$a}'"
        );
    }
    echo "OK: remote agent {$agent} set {$status} on {$campaign}\n";
    exit;
}

/**
 * Queue dialable leads from the campaign's active lists as READY (no local-call-time
 * filter — AST_VDhopper skips foreign numbers like +92 outside US call windows).
 */
function ai_fronter_load_hopper(mysqli $db, string $campaign): void
{
    $c = $db->real_escape_string($campaign);
    $res = $db->query("SELECT dial_statuses, hopper_level FROM vicidial_campaigns WHERE campaign_id='{$c}'");
    $camp = $res ? $res->fetch_assoc() : null;
    if (!$camp) {
        echo "ERROR: campaign {$campaign} not found\n";
        return;
    }
    $statuses = array_values(array_filter(
        preg_split('/\s+/', trim((string) $camp['dial_statuses'])),
        function ($s) { return $s !== '' && $s !== '-'; }
    ));
    if (!$statuses) {
        $statuses = ['NEW'];
    }
    $statusSql = "'" . implode("','", array_map([$db, 'real_escape_string'], $statuses)) . "'";
    $limit = max(1, (int) $camp['hopper_level']);

    $lists = [];
    $res = $db->query("SELECT list_id FROM vicidial_lists WHERE campaign_id='{$c}' AND active='Y'");
    while ($res && ($row = $res->fetch_assoc())) {
        $lists[] = (int) $row['list_id'];
    }
    if (!$lists) {
        echo "ERROR: no active lists for campaign {$campaign} (ViciDial Admin -> Lists -> Active=Y)\n";
        return;
    }
    $listSql = implode(',', $lists);

    $res = $db->query("SELECT COUNT(*) n FROM vicidial_hopper WHERE campaign_id='{$c}' AND status='READY'");
    $already = (int) (($res ? $res->fetch_assoc() : ['n' => 0])['n']);

    $db->query(
        "INSERT INTO vicidial_hopper (lead_id, campaign_id, status, list_id, gmt_offset_now, state, priority, source, vendor_lead_code)
         SELECT l.lead_id, '{$c}', 'READY', l.list_id, l.gmt_offset_now, l.state, 0, 'M', l.vendor_lead_code
         FROM vicidial_list l
         LEFT JOIN vicidial_hopper h ON h.lead_id = l.lead_id
         LEFT JOIN vicidial_dnc d ON d.phone_number = l.phone_number
         WHERE l.list_id IN ({$listSql})
           AND l.status IN ({$statusSql})
           AND l.called_since_last_reset = 'N'
           AND h.lead_id IS NULL
           AND d.phone_number IS NULL
           AND NOT EXISTS (
             SELECT 1 FROM vicidial_list dup
             WHERE dup.list_id IN ({$listSql})
               AND dup.phone_number = l.phone_number
               AND dup.status IN ({$statusSql})
               AND dup.called_since_last_reset = 'N'
               AND dup.lead_id > l.lead_id
           )
           AND NOT EXISTS (
             SELECT 1 FROM vicidial_hopper hq
             JOIN vicidial_list ql ON ql.lead_id = hq.lead_id
             WHERE hq.campaign_id = '{$c}' AND ql.phone_number = l.phone_number
           )
         ORDER BY l.lead_id
         LIMIT {$limit}"
    );
    $loaded = max(0, $db->affected_rows);

    if ($loaded + $already === 0) {
        $counts = [];
        $res = $db->query("SELECT status, COUNT(*) n FROM vicidial_list WHERE list_id IN ({$listSql}) GROUP BY status");
        while ($res && ($row = $res->fetch_assoc())) {
            $counts[] = "{$row['status']}={$row['n']}";
        }
        echo "ERROR: no dialable leads in lists {$listSql} (dial statuses: " . implode(' ', $statuses)
            . '; leads by status: ' . ($counts ? implode(', ', $counts) : 'none') . ")\n";
        return;
    }
    echo "OK: hopper loaded {$loaded} lead(s), {$already} already queued, lists {$listSql}\n";
}

/**
 * Pre-dial checks. First line is "OK: ..." or "ERROR: <first problem>"; detail lines follow.
 * Stuck calls whose channel is gone are cleared and the remote agent is set READY.
 */
function ai_fronter_preflight(mysqli $db, string $campaign, string $agent): void
{
    $problems = [];
    $notes = [];
    $c = $db->real_escape_string($campaign);
    $a = $db->real_escape_string($agent);

    $ps = (string) @shell_exec('ps -eo args 2>/dev/null');
    if ($ps !== '') {
        foreach (['AST_update' => 'ASTupdate', 'AST_VDauto_dial' => 'ASTVDauto', 'AST_VDremote_agents' => 'ASTVDremote'] as $needle => $label) {
            if (strpos($ps, $needle) === false) {
                $problems[] = "dialer process {$label} not running (run ADMIN_keepalive_ALL.pl --cu3way)";
            }
        }
        if (strpos($ps, 'asterisk') === false) {
            $problems[] = 'Asterisk not running';
        }
    } else {
        $notes[] = 'process check skipped (shell_exec disabled)';
    }

    // Read the kernel's listen table — SELinux usually blocks httpd from connecting out.
    $listening = false;
    foreach (['/proc/net/tcp', '/proc/net/tcp6'] as $procFile) {
        foreach ((array) @file($procFile) as $line) {
            $cols = preg_split('/\s+/', trim((string) $line));
            if (isset($cols[3]) && $cols[3] === '0A' && substr($cols[1], -5) === ':2384') {
                $listening = true;
            }
        }
    }
    if ($listening) {
        $notes[] = 'AudioSocket bridge listening on 9092';
    } else {
        $problems[] = "AudioSocket bridge not listening on 9092 (systemctl restart ai-fronter-audiosocket@{$agent})";
    }

    $live = [];
    foreach (['live_sip_channels', 'live_channels'] as $table) {
        $res = $db->query("SELECT channel FROM {$table}");
        while ($res && ($row = $res->fetch_assoc())) {
            $live[$row['channel']] = true;
        }
    }

    $stale = 0;
    $active = 0;
    $res = $db->query("SELECT auto_call_id, channel, call_time FROM vicidial_auto_calls WHERE campaign_id='{$c}'");
    while ($res && ($row = $res->fetch_assoc())) {
        $age = time() - strtotime($row['call_time']);
        if (($row['channel'] !== '' && isset($live[$row['channel']])) || $age < 120) {
            $active++;
        } else {
            $db->query('DELETE FROM vicidial_auto_calls WHERE auto_call_id=' . (int) $row['auto_call_id']);
            $stale++;
        }
    }
    if ($stale > 0) {
        $notes[] = "cleared {$stale} stuck call(s) from vicidial_auto_calls";
    }
    if ($active > 0) {
        $problems[] = "{$active} call(s) still in progress on {$campaign} — hang up and retry";
    }

    $res = $db->query("SELECT status FROM vicidial_live_agents WHERE user='{$a}'");
    $agentRow = $res ? $res->fetch_assoc() : null;
    if (!$agentRow) {
        $problems[] = "remote agent {$agent} not logged in (vicidial_remote_agents status ACTIVE?)";
    } elseif ($active === 0 && $agentRow['status'] !== 'READY') {
        $db->query("UPDATE vicidial_live_agents SET status='READY', lead_id=0, uniqueid='', callerid='', channel='', comments='' WHERE user='{$a}'");
        $notes[] = "agent {$agent} was {$agentRow['status']} — reset to READY";
    } else {
        $notes[] = "agent {$agent} {$agentRow['status']}";
    }

    $disk = @disk_free_space('/');
    $total = @disk_total_space('/');
    if ($disk !== false && $total) {
        $used = (int) round(100 - ($disk / $total) * 100);
        if ($used >= 95) {
            $problems[] = "disk {$used}% full (truncate /var/log/astguiclient/conf_telnet_log.txt)";
        }
    }

    echo $problems ? 'ERROR: ' . $problems[0] . "\n" : "OK: dialer ready\n";
    foreach (array_merge(array_slice($problems, 1), $notes) as $line) {
        echo "- {$line}\n";
    }
}

$stmt = $mysqli->prepare(
    'SELECT lead_id FROM vicidial_list WHERE phone_code=? AND phone_number=? ORDER BY lead_id DESC LIMIT 1'
);
$stmt->bind_param('ss', $pcode, $pnum);
$stmt->execute();
$res = $stmt->get_result();
$row = $res ? $res->fetch_assoc() : null;
$leadId = $row['lead_id'] ?? null;
$stmt->close();

if (!$leadId) {
    echo "ERROR: lead not found\n";
    exit;
}

$mysqli->query(
    "DELETE h FROM vicidial_hopper h
     INNER JOIN vicidial_list l ON h.lead_id = l.lead_id
     WHERE h.campaign_id = '" . $mysqli->real_escape_string($campaign) . "'
       AND NOT (l.phone_code = '" . $mysqli->real_escape_string($pcode) . "'
                AND l.phone_number = '" . $mysqli->real_escape_string($pnum) . "')"
);

$mysqli->query(
    "DELETE FROM vicidial_hopper WHERE campaign_id = '" . $mysqli->real_escape_string($campaign) . "'
     AND lead_id <> " . (int) $leadId
);

$mysqli->query(
    "INSERT INTO vicidial_hopper (lead_id, campaign_id, status, priority, source)
     SELECT " . (int) $leadId . ", '" . $mysqli->real_escape_string($campaign) . "', 'READY', 99, 'MANUAL'
     FROM DUAL
     WHERE NOT EXISTS (
       SELECT 1 FROM vicidial_hopper WHERE campaign_id = '" . $mysqli->real_escape_string($campaign) . "'
         AND lead_id = " . (int) $leadId . "
     )"
);

$mysqli->query(
    "UPDATE vicidial_hopper SET status='READY', priority=99
     WHERE campaign_id = '" . $mysqli->real_escape_string($campaign) . "' AND lead_id = " . (int) $leadId
);

$mysqli->query(
    "UPDATE vicidial_list SET status='NEW', called_count=0, called_since_last_reset='N',
     campaign_id = '" . $mysqli->real_escape_string($campaign) . "'
     WHERE lead_id = " . (int) $leadId
);

echo "OK: hopper READY lead_id={$leadId} campaign={$campaign} +{$pcode}{$pnum}\n";
