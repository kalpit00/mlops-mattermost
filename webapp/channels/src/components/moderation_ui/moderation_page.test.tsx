import React from 'react';

import {fireEvent, renderWithContext, screen} from 'tests/react_testing_utils';

import ModerationPage from './moderation_page';

describe('components/moderation_ui/ModerationPage', () => {
    test('renders moderation list and detail', () => {
        renderWithContext(<ModerationPage/>);

        expect(screen.getByText('Moderation')).toBeInTheDocument();
        expect(screen.getByText('Alerted Messages')).toBeInTheDocument();
        expect(screen.getByText('Review Alert')).toBeInTheDocument();
    });

    test('updates selected alert decision in UI', () => {
        renderWithContext(<ModerationPage/>);

        fireEvent.click(screen.getAllByText('Keep')[0]);
        expect(screen.getByText('reviewed')).toBeInTheDocument();
        expect(screen.getByText('keep')).toBeInTheDocument();
    });
});
