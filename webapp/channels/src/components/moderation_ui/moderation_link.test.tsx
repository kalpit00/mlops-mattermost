import React from 'react';
import {createMemoryHistory} from 'history';
import {Router} from 'react-router-dom';

import {renderWithContext, screen} from 'tests/react_testing_utils';

import ModerationLink from './moderation_link';

describe('components/moderation_ui/ModerationLink', () => {
    test('renders moderation sidebar button with route', () => {
        const history = createMemoryHistory({initialEntries: ['/myteam/channels/town-square']});

        renderWithContext(
            <Router history={history}>
                <ModerationLink/>
            </Router>,
        );

        const link = screen.getByRole('link', {name: 'Moderation'});
        expect(link).toHaveAttribute('href', '/myteam/moderation');
    });
});
