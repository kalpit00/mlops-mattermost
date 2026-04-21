import React, {memo} from 'react';
import {FormattedMessage} from 'react-intl';
import {NavLink, useLocation} from 'react-router-dom';

export default memo(function ModerationLink() {
    const {pathname} = useLocation();
    const team = pathname.split('/')[1] || '';

    return (
        <ul className='SidebarDrafts NavGroupContent nav nav-pills__container'>
            <li
                className='SidebarChannel'
                tabIndex={-1}
                id='sidebar-moderation-button'
            >
                <NavLink
                    to={`/${team}/moderation`}
                    id='sidebarItem_moderation'
                    activeClassName='active'
                    draggable='false'
                    className='SidebarLink sidebar-item'
                    tabIndex={0}
                >
                    <i className='icon icon-alert-outline'/>
                    <div className='SidebarChannelLinkLabel_wrapper'>
                        <span className='SidebarChannelLinkLabel sidebar-item__name'>
                            <FormattedMessage
                                id='moderation_ui.sidebar_link'
                                defaultMessage='Moderation'
                            />
                        </span>
                    </div>
                </NavLink>
            </li>
        </ul>
    );
});
