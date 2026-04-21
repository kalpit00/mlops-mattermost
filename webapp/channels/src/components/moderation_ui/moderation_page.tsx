import React, {useMemo, useState} from 'react';
import {FormattedMessage} from 'react-intl';

import ModerationDetail from './moderation_detail';
import ModerationList from './moderation_list';
import {mockAlerts, type ModerationAlert} from './mock_alerts';

import './moderation_page.scss';

export default function ModerationPage() {
    const [alerts, setAlerts] = useState<ModerationAlert[]>(mockAlerts);
    const [selectedId, setSelectedId] = useState<string | null>(alerts[0]?.id || null);

    const selectedAlert = useMemo(() => {
        return alerts.find((a) => a.id === selectedId) || null;
    }, [alerts, selectedId]);

    const onDecision = (decision: 'keep' | 'escalate' | 'remove') => {
        if (!selectedId) {
            return;
        }

        setAlerts((prev) => prev.map((alert) => {
            if (alert.id !== selectedId) {
                return alert;
            }

            return {
                ...alert,
                decision,
                status: 'reviewed',
            };
        }));
    };

    return (
        <div className='ModerationPage app__content'>
            <header>
                <h2>
                    <FormattedMessage
                        id='moderation_ui.title'
                        defaultMessage='Moderation'
                    />
                </h2>
            </header>
            <div className='layout'>
                <ModerationList
                    alerts={alerts}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                />
                <ModerationDetail
                    alert={selectedAlert}
                    onDecision={onDecision}
                />
            </div>
        </div>
    );
}
